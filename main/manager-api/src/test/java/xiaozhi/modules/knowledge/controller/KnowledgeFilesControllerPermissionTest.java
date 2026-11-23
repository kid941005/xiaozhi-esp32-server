package xiaozhi.modules.knowledge.controller;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.mockStatic;
import static org.mockito.Mockito.when;

import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

import org.junit.jupiter.api.Test;
import org.mockito.MockedStatic;

import xiaozhi.common.exception.ErrorCode;
import xiaozhi.common.exception.RenException;
import xiaozhi.common.utils.MessageUtils;
import xiaozhi.modules.knowledge.service.KnowledgeBaseService;
import xiaozhi.modules.knowledge.service.KnowledgeFilesService;
import xiaozhi.modules.security.user.SecurityUser;

/**
 * 知识库不存在时不能解引用 null 抛 NPE（500），应统一按无权限拒绝（#H5）。
 */
class KnowledgeFilesControllerPermissionTest {

    @Test
    void missingKnowledgeBaseIsRejectedWithPermissionError() throws Exception {
        KnowledgeBaseService knowledgeBaseService = mock(KnowledgeBaseService.class);
        when(knowledgeBaseService.getByDatasetId("ds-1")).thenReturn(null);
        KnowledgeFilesController controller = new KnowledgeFilesController(
                mock(KnowledgeFilesService.class), knowledgeBaseService);

        Method method = KnowledgeFilesController.class
                .getDeclaredMethod("validateKnowledgeBasePermission", String.class);
        method.setAccessible(true);

        // RenException 构造器会走 MessageUtils → SpringContextUtils.getBean，单测里没有 Spring 容器，
        // 所以这里把消息解析桩掉。
        try (MockedStatic<MessageUtils> messageUtils = mockStatic(MessageUtils.class);
                MockedStatic<SecurityUser> securityUser = mockStatic(SecurityUser.class)) {
            messageUtils.when(() -> MessageUtils.getMessage(anyInt())).thenReturn("没有权限");
            securityUser.when(SecurityUser::getUserId).thenReturn(1L);

            InvocationTargetException thrown = org.junit.jupiter.api.Assertions.assertThrows(
                    InvocationTargetException.class, () -> method.invoke(controller, "ds-1"));
            assertTrue(thrown.getCause() instanceof RenException,
                    "应抛出 RenException 而不是 NPE，实际: " + thrown.getCause());
            assertEquals(ErrorCode.NO_PERMISSION, ((RenException) thrown.getCause()).getCode());
        }
    }
}
