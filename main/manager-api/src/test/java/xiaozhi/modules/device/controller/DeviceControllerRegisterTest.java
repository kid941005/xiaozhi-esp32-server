package xiaozhi.modules.device.controller;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

import xiaozhi.common.exception.ErrorCode;
import xiaozhi.common.redis.RedisUtils;
import xiaozhi.common.utils.Result;
import xiaozhi.modules.device.dto.DeviceRegisterDTO;

/**
 * 设备注册验证码：必须是固定六位纯数字（SecureRandom 生成），碰撞时有重试上限（#H3）。
 */
class DeviceControllerRegisterTest {

    /** 用内存 Map 代替 Redis，避免 Mockito 对 RedisUtils 的字节码增强。 */
    private static class MemoryRedisUtils extends RedisUtils {
        private final Map<String, Object> store = new HashMap<>();
        private final boolean alwaysOccupied;
        private int getCalls = 0;
        private int setCalls = 0;

        MemoryRedisUtils(boolean alwaysOccupied) {
            this.alwaysOccupied = alwaysOccupied;
        }

        @Override
        public Object get(String key) {
            getCalls++;
            return alwaysOccupied ? "occupied" : store.get(key);
        }

        @Override
        public void set(String key, Object value) {
            setCalls++;
            store.put(key, value);
        }
    }

    private static DeviceController controller(RedisUtils redisUtils) {
        return new DeviceController(null, null, redisUtils, null);
    }

    private static DeviceRegisterDTO dto() {
        DeviceRegisterDTO dto = new DeviceRegisterDTO();
        dto.setMacAddress("aa:bb:cc:dd:ee:ff");
        return dto;
    }

    @Test
    void generatedCodeIsSixDigitNumericAndStoredWithMac() {
        MemoryRedisUtils redis = new MemoryRedisUtils(false);

        Result<String> result = controller(redis).registerDevice(dto());

        assertEquals(0, result.getCode());
        assertTrue(result.getData().matches("\\d{6}"), "code should be 6 digits: " + result.getData());
        assertEquals("aa:bb:cc:dd:ee:ff", redis.store.get("sys:device:captcha:" + result.getData()));
        assertEquals(1, redis.setCalls);
    }

    @Test
    void givesUpAfterRetryLimitWhenEveryCodeIsTaken() {
        MemoryRedisUtils redis = new MemoryRedisUtils(true);

        Result<String> result = controller(redis).registerDevice(dto());

        assertEquals(ErrorCode.INTERNAL_SERVER_ERROR, result.getCode());
        assertNull(result.getData());
        assertEquals(DeviceController.CAPTCHA_MAX_RETRY, redis.getCalls);
        assertEquals(0, redis.setCalls);
    }

    @Test
    void allocateDeviceCodeReturnsNullWhenLookupNeverFree() {
        AtomicInteger lookups = new AtomicInteger();
        String code = controller(new MemoryRedisUtils(false))
                .allocateDeviceCode(key -> {
                    lookups.incrementAndGet();
                    return "taken";
                });

        assertNull(code);
        assertEquals(10, lookups.get());
    }
}
