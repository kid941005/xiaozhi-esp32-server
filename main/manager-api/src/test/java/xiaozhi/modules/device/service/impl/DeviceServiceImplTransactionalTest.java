package xiaozhi.modules.device.service.impl;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.lang.reflect.Method;

import org.junit.jupiter.api.Test;
import org.springframework.transaction.annotation.Transactional;

/**
 * 多写操作必须在一个事务内，避免「设备已绑定但通讯录未清理」这类半成品状态（#H4）。
 */
class DeviceServiceImplTransactionalTest {

    private static final String[] MULTI_WRITE_METHODS = {"deviceActivation", "unbindDevice", "manualAddDevice"};

    @Test
    void multiWriteMethodsAreTransactionalWithExceptionRollback() throws Exception {
        for (String name : MULTI_WRITE_METHODS) {
            Method target = null;
            for (Method candidate : DeviceServiceImpl.class.getMethods()) {
                if (candidate.getName().equals(name)) {
                    target = candidate;
                    break;
                }
            }
            assertNotNull(target, name + " 方法不存在");
            Transactional tx = target.getAnnotation(Transactional.class);
            assertNotNull(tx, name + " 缺少 @Transactional");
            boolean rollbackForException = false;
            for (Class<?> rollback : tx.rollbackFor()) {
                if (rollback == Exception.class) {
                    rollbackForException = true;
                    break;
                }
            }
            assertTrue(rollbackForException, name + " 需要 rollbackFor = Exception.class");
        }
    }
}
