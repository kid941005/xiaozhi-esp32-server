package xiaozhi.modules.config.init;

import java.util.List;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.DependsOn;

import jakarta.annotation.PostConstruct;
import xiaozhi.common.constant.Constant;
import xiaozhi.common.redis.RedisKeys;
import xiaozhi.common.redis.RedisUtils;
import xiaozhi.modules.config.service.ConfigService;
import xiaozhi.modules.device.service.DeviceAddressBookService;
import xiaozhi.modules.sys.service.SysParamsService;

@Configuration
@DependsOn("liquibase")
public class SystemInitConfig {

    @Autowired
    private SysParamsService sysParamsService;

    @Autowired
    private ConfigService configService;

    @Autowired
    private RedisUtils redisUtils;

    @Autowired
    private DeviceAddressBookService deviceAddressBookService;

    @PostConstruct
    public void init() {
        // 检查版本号
        String redisVersion = (String) redisUtils.get(RedisKeys.getVersionKey());
        if (!Constant.VERSION.equals(redisVersion)) {
            // 版本不一致时只清理本应用的缓存前缀，禁止 FLUSHALL 误删共享 Redis 中其他应用的数据
            redisUtils.deleteByPrefixes(List.of(
                    "sys:", "model:", "timbre:", "agent:", "device:", "ota:",
                    "sms:", "knowledge:", "voiceClone:", "tmp_register_mac:", "server:"));
            // 存储新版本号
            redisUtils.set(RedisKeys.getVersionKey(), Constant.VERSION);
        }

        sysParamsService.initServerSecret();
        configService.getConfig(false);

        // 初始化设备通讯录缓存
        deviceAddressBookService.refreshCache();
    }
}