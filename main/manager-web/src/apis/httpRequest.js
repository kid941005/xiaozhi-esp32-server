import Fly from 'flyio/dist/npm/fly';
import store from '../store/index';
import Constant from '../utils/constant';
import { getServiceUrl } from '../apis/api';
import { goToPage, isNotNull, showDanger, showWarning } from '../utils/index';
import i18n from '../i18n/index';

const fly = new Fly()
// 设置超时
fly.config.timeout = 30000

// 独立 fly 实例给 silent refresh 用，避免任何回调链回到 sendRequest
const refreshFly = new Fly()
refreshFly.config.timeout = 30000

// silent refresh：剩 1h 触发换 token，单飞锁避免并发
const REFRESH_AHEAD_MS = 60 * 60 * 1000
let refreshPromise = null

function getTokenExpireAt() {
    // 与 persistTokenExpireAt 同源读 localStorage（store 走的是 state.token 缓存，
    // 刚写入 localStorage 后再走 store 拿不到补写的 _localStoredAt）
    const raw = localStorage.getItem('token')
    if (!raw) return 0
    try {
        const parsed = JSON.parse(raw)
        if (!parsed || !parsed.expire) return 0
        // login.vue 写入 store 时是 setToken(now)，token 对象里没有 createdAt；
        // 用 _localStoredAt 作为本地落地时间基准
        return (parsed._localStoredAt || 0) + parsed.expire * 1000
    } catch (e) {
        return 0
    }
}

// 首次见到该 token 时记下落地时间；同步刷新 localStorage 与 store，保证两端一致
function persistTokenExpireAt() {
    const raw = localStorage.getItem('token')
    if (!raw) return
    try {
        const parsed = JSON.parse(raw)
        if (parsed && parsed.expire && !parsed._localStoredAt) {
            parsed._localStoredAt = Date.now()
            const next = JSON.stringify(parsed)
            localStorage.setItem('token', next)
            store.commit('setToken', next)
        }
    } catch (e) { /* ignore */ }
}

function shouldRefresh() {
    persistTokenExpireAt()
    const exp = getTokenExpireAt()
    if (!exp) return false
    return exp - Date.now() < REFRESH_AHEAD_MS
}

function doRefresh() {
    // 直接走 fly.request，绕过 sendRequest，避免死循环触发 silent refresh
    const raw = localStorage.getItem('token')
    if (!raw) return Promise.reject(new Error('no token'))
    let bearer
    try {
        bearer = JSON.parse(raw).token
    } catch (e) {
        return Promise.reject(e)
    }
    return refreshFly.request(getServiceUrl() + '/user/refresh', {}, {
        method: 'POST',
        headers: { Authorization: 'Bearer ' + bearer }
    }).then((res) => {
        const body = res && res.data
        if (!body || (body.code !== 0 && body.code !== 'success')) {
            throw new Error('refresh failed: ' + (body && body.msg))
        }
        const newDto = body.data
        newDto._localStoredAt = Date.now()
        store.commit('setToken', JSON.stringify(newDto))
        return newDto
    })
}

function triggerSilentRefresh() {
    if (!refreshPromise) {
        refreshPromise = doRefresh().catch((err) => {
            store.commit('clearAuth')
            goToPage(Constant.PAGE.LOGIN, true)
            throw err
        }).finally(() => {
            refreshPromise = null
        })
    }
    return refreshPromise
}

/**
 * Request服务封装
 */
export default {
    sendRequest,
    reAjaxFun,
    clearRequestTime,
    triggerSilentRefresh
}

function sendRequest() {
    return {
        _sucCallback: null,
        _failCallback: null,
        _networkFailCallback: null,
        _method: 'GET',
        _data: {},
        _header: { 'content-type': 'application/json; charset=utf-8' },
        _url: '',
        _responseType: undefined, // 新增响应类型字段
        'send'() {
            // 设置语言请求头
            const currentLang = i18n.locale;
            // 转换语言代码格式，将zh_CN转换为zh-CN
            let acceptLanguage = currentLang.replace('_', '-');
            // 为英语添加默认地区代码
            if (acceptLanguage === 'en') {
                acceptLanguage = 'en-US';
            }
            this._header['Accept-Language'] = acceptLanguage;

            const doSend = () => {
                if (isNotNull(store.getters.getToken)) {
                    try {
                        const tokenInfo = JSON.parse(store.getters.getToken)
                        if (tokenInfo && tokenInfo.token) {
                            this._header.Authorization = 'Bearer ' + tokenInfo.token
                        }
                    } catch (e) {
                        // token 已损坏：清理登录态并回登录页，避免带着非法 token 继续请求
                        store.commit('clearAuth')
                        goToPage(Constant.PAGE.LOGIN, true)
                        return
                    }
                }

                // 打印请求信息
                // 只有幂等请求才允许上层在网络错误时自动重试；
                // 非幂等写操作（POST/PUT/DELETE/PATCH）网络超时后重发可能造成重复提交
                const method = (this._method || 'GET').toUpperCase()
                const idempotent = ['GET', 'HEAD', 'OPTIONS'].includes(method)
                const networkFailCallback = idempotent ? this._networkFailCallback : null

                fly.request(this._url, this._data, {
                    method: this._method,
                    headers: this._header,
                    responseType: this._responseType
                }).then((res) => {
                    const error = httpHandlerError(res, this._failCallback, networkFailCallback);
                    if (error) {
                        return
                    }

                    if (this._sucCallback) {
                        this._sucCallback(res)
                    }
                }).catch((res) => {
                    // 打印失败响应
                    console.log('catch', res)
                    httpHandlerError(res, this._failCallback, networkFailCallback)
                })
            }

            // 剩 1h 内过期就先 silent refresh 再发，确保请求带新 token
            if (shouldRefresh()) {
                triggerSilentRefresh().then(doSend).catch(() => {
                    // 触发 refresh 后被拦截跳登录，这里什么都不用做
                })
            } else {
                doSend()
            }
            return this
        },
        'success'(callback) {
            this._sucCallback = callback
            return this
        },
        'fail'(callback) {
            this._failCallback = callback
            return this
        },
        'networkFail'(callback) {
            this._networkFailCallback = callback
            return this
        },
        'url'(url) {
            if (url) {
                url = url.replaceAll('$', '/')
            }
            this._url = url
            return this
        },
        'data'(data) {
            this._data = data
            return this
        },
        'method'(method) {
            this._method = method
            return this
        },
        'header'(header) {
            this._header = header
            return this
        },
        'showLoading'(showLoading) {
            this._showLoading = showLoading
            return this
        },
        'async'(flag) {
            this.async = flag
        },
        // 新增类型设置方法
        'type'(responseType) {
            this._responseType = responseType;
            return this;
        }
    }
}

/**
 * Info 请求完成后返回信息
 * failCallback 回调函数
 * networkFailCallback 回调函数
 */
// 在错误处理函数中添加日志
function httpHandlerError(info, failCallback, networkFailCallback) {

    /** 请求成功，退出该函数 可以根据项目需求来判断是否请求成功。这里判断的是status为200的时候是成功 */
    if (info.status === 200) {
        const data = info.data
        // 文件下载（blob/arraybuffer）没有业务 code，直接视为成功
        const isBinary = (typeof Blob !== 'undefined' && data instanceof Blob) ||
            (typeof ArrayBuffer !== 'undefined' && data instanceof ArrayBuffer)
        const code = data && typeof data === 'object' ? data.code : undefined
        if (isBinary || code === 'success' || code === 0) {
            return false
        }
        if (code === 401) {
            store.commit('clearAuth');
            goToPage(Constant.PAGE.LOGIN, true);
            return true
        }
        // 业务失败：交给 failCallback 或统一提示，不做网络重试
        const errorMessage = (data && data.msg) || '请求处理失败'
        if (failCallback) {
            failCallback(info)
        } else {
            showDanger(errorMessage)
        }
        return true
    }

    // HTTP 401/403：登录态失效或权限不足，不能当作网络错误重试
    if (info.status === 401) {
        store.commit('clearAuth');
        goToPage(Constant.PAGE.LOGIN, true);
        return true
    }
    if (info.status === 403) {
        const msg = (info.data && info.data.msg) || '没有权限执行该操作'
        if (failCallback) {
            failCallback(info)
        } else {
            showDanger(msg)
        }
        return true
    }
    // 其余 HTTP 错误（4xx/5xx）属于服务端业务错误，同样不触发网络重试，避免写操作被重复提交
    if (info.status >= 400) {
        const msg = (info.data && info.data.msg) || `请求失败【${info.status}】`
        if (failCallback) {
            failCallback(info)
        } else {
            showDanger(msg)
        }
        return true
    }
    // status 为 0/undefined 才是真正的网络错误（超时、断网、CORS 等）
    if (networkFailCallback) {
        networkFailCallback(info)
    } else {
        showDanger(`网络请求出现了错误【${info.status}】`)
    }
    return true
}

let requestTime = 0
let reAjaxSec = 2

function reAjaxFun(fn) {
    let nowTimeSec = new Date().getTime() / 1000
    if (requestTime === 0) {
        requestTime = nowTimeSec
    }
    let ajaxIndex = parseInt((nowTimeSec - requestTime) / reAjaxSec)
    if (ajaxIndex > 10) {
        showWarning('似乎无法连接服务器')
    } else {
        showWarning('正在连接服务器(' + ajaxIndex + ')')
    }
    if (ajaxIndex < 10 && fn) {
        setTimeout(() => {
            fn()
        }, reAjaxSec * 1000)
    }
}

function clearRequestTime() {
    requestTime = 0
}