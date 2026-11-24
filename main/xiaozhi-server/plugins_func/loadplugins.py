import importlib
import os
import pkgutil
import re
from typing import Dict, List, Optional, Sequence, Set

from config.logger import setup_logging

TAG = __name__

logger = setup_logging()

# 源码级匹配 @register_function("name") / @register_function(name="name")，
# 支持跨行写法（@register_function(\n    "name", ...）
_REGISTER_FUNC_RE = re.compile(
    r"@register_function\(\s*(?:name\s*=\s*)?[rRuU]?[\"']([^\"']+)[\"']"
)

# 函数名 -> 模块名、模块名 -> 函数名列表（由源码扫描得到，不 import 子模块）
_FUNC_TO_MODULE: Optional[Dict[str, str]] = None
_MODULE_TO_FUNCS: Optional[Dict[str, List[str]]] = None

# 进程内已成功 import 的插件模块名
_LOADED_MODULES: Set[str] = set()


def auto_import_modules(package_name):
    """（保留原行为）导入包内所有模块。

    注意：这会执行全部插件模块的模块级代码，已不再由连接初始化路径调用，
    仅在需要全量兜底时使用。
    """
    package = importlib.import_module(package_name)
    package_path = package.__path__

    for _, module_name, _ in pkgutil.iter_modules(package_path):
        full_module_name = f"{package_name}.{module_name}"
        importlib.import_module(full_module_name)


def auto_import_modules_soft(package_name, log=None):
    """逐个模块容错导入：单个模块失败不影响其它模块。

    Returns:
        (loaded_modules, failed_modules)
    """
    log = log or logger
    package = importlib.import_module(package_name)
    package_path = package.__path__

    loaded: List[str] = []
    failed: List[str] = []
    for _, module_name, _ in pkgutil.iter_modules(package_path):
        full_module_name = f"{package_name}.{module_name}"
        try:
            importlib.import_module(full_module_name)
            _LOADED_MODULES.add(module_name)
            loaded.append(module_name)
        except Exception as e:
            failed.append(module_name)
            log.bind(tag=TAG).error(f"插件模块加载失败: {module_name}: {e}")
    return loaded, failed


def scan_plugin_index(package_name: str = "plugins_func.functions", force: bool = False):
    """扫描插件源码建立索引：只读文件，不 import 子模块、不执行插件代码。

    Returns:
        (function_name -> module_name, module_name -> [function_name, ...])
    """
    global _FUNC_TO_MODULE, _MODULE_TO_FUNCS
    if _FUNC_TO_MODULE is not None and not force:
        return _FUNC_TO_MODULE, _MODULE_TO_FUNCS

    package = importlib.import_module(package_name)
    base_dir = list(package.__path__)[0]

    func_to_module: Dict[str, str] = {}
    module_to_funcs: Dict[str, List[str]] = {}
    try:
        filenames = sorted(os.listdir(base_dir))
    except OSError as e:
        logger.bind(tag=TAG).error(f"扫描插件目录失败: {base_dir}: {e}")
        filenames = []

    for filename in filenames:
        if not filename.endswith(".py") or filename.startswith("_"):
            continue
        module_name = filename[:-3]
        try:
            with open(os.path.join(base_dir, filename), "r", encoding="utf-8") as f:
                source = f.read()
        except OSError as e:
            logger.bind(tag=TAG).warning(f"读取插件文件失败: {filename}: {e}")
            continue

        names = _REGISTER_FUNC_RE.findall(source)
        if not names:
            continue
        module_to_funcs[module_name] = names
        for name in names:
            # 同名函数以先扫描到的模块为准（与导入顺序无关，保证结果稳定）
            func_to_module.setdefault(name, module_name)

    _FUNC_TO_MODULE = func_to_module
    _MODULE_TO_FUNCS = module_to_funcs
    logger.bind(tag=TAG).debug(
        f"插件索引建立完成: {len(module_to_funcs)} 个模块 / {len(func_to_module)} 个函数"
    )
    return func_to_module, module_to_funcs


def import_plugin_module(
    module_name: str, package_name: str = "plugins_func.functions", log=None
) -> bool:
    """导入单个插件模块（幂等）。失败只记日志并返回 False。"""
    if module_name in _LOADED_MODULES:
        return True
    log = log or logger
    try:
        importlib.import_module(f"{package_name}.{module_name}")
        _LOADED_MODULES.add(module_name)
        return True
    except Exception as e:
        log.bind(tag=TAG).error(f"插件模块加载失败: {module_name}: {e}")
        return False


def ensure_plugins_loaded(
    names: Sequence[str],
    package_name: str = "plugins_func.functions",
    fallback_all: bool = True,
    log=None,
) -> List[str]:
    """按需加载插件模块：names 中既可以是函数名，也可以是模块名。

    - 命中索引的，只 import 它所在的那一个模块；
    - 未命中的名字（MCP/设备工具、动态注册的插件）在 fallback_all=True 时
      回退为「逐个容错全量导入」，保证不漏，同时坏模块不会拖垮整体。

    Returns:
        本次实际导入（或此前已导入）的模块名列表
    """
    log = log or logger
    func_to_module, module_to_funcs = scan_plugin_index(package_name)

    modules: List[str] = []
    unknown: List[str] = []
    seen: Set[str] = set()

    for name in names or []:
        if not name:
            continue
        if name in module_to_funcs:
            module = name
        else:
            module = func_to_module.get(name)
        if module is None:
            unknown.append(name)
            continue
        if module in seen:
            continue
        seen.add(module)
        modules.append(module)

    imported = [m for m in modules if import_plugin_module(m, package_name, log)]

    if unknown and fallback_all:
        log.bind(tag=TAG).debug(f"以下名字未命中插件索引，回退全量导入: {unknown}")
        auto_import_modules_soft(package_name, log)

    return imported


def reset_plugin_index():
    """清空索引与已加载缓存（测试用）。"""
    global _FUNC_TO_MODULE, _MODULE_TO_FUNCS
    _FUNC_TO_MODULE = None
    _MODULE_TO_FUNCS = None
    _LOADED_MODULES.clear()
