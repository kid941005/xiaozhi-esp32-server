-- 飞牛音乐网关（fnmusic-gateway）插件：让智控台可以启用并配置该插件
START TRANSACTION;

INSERT INTO sys_params (id, param_code, param_value, value_type, param_type, remark, creator, create_date, updater, update_date)
VALUES (510, 'plugins.fnmusic_gateway.base_url', '', 'string', 1, '飞牛音乐网关地址，例如 http://192.168.50.100:8766，留空表示不启用', 1, NOW(), 1, NOW()),
       (511, 'plugins.fnmusic_gateway.enabled', 'true', 'boolean', 1, '是否启用飞牛音乐网关插件', 1, NOW(), 1, NOW()),
       (512, 'plugins.fnmusic_gateway.timeout', '10', 'number', 1, '请求飞牛音乐网关的超时时间（秒）', 1, NOW(), 1, NOW()),
       (513, 'plugins.fnmusic_gateway.quality', '', 'string', 1, '音质参数，留空使用网关默认值', 1, NOW(), 1, NOW());

INSERT INTO ai_model_provider (id, model_type, provider_code, name, fields,
                               sort, creator, create_date, updater, update_date)
VALUES ('SYSTEM_PLUGIN_FNMUSIC',
        'Plugin',
        'fnmusic_gateway',
        '飞牛音乐网关',
        JSON_ARRAY(
                JSON_OBJECT(
                        'key', 'base_url',
                        'type', 'string',
                        'label', '网关地址',
                        'default', (SELECT param_value FROM sys_params WHERE param_code = 'plugins.fnmusic_gateway.base_url')
                ),
                JSON_OBJECT(
                        'key', 'enabled',
                        'type', 'boolean',
                        'label', '是否启用',
                        'default', (SELECT param_value FROM sys_params WHERE param_code = 'plugins.fnmusic_gateway.enabled')
                ),
                JSON_OBJECT(
                        'key', 'timeout',
                        'type', 'number',
                        'label', '超时时间（秒）',
                        'default', (SELECT param_value FROM sys_params WHERE param_code = 'plugins.fnmusic_gateway.timeout')
                ),
                JSON_OBJECT(
                        'key', 'quality',
                        'type', 'string',
                        'label', '音质参数',
                        'default', (SELECT param_value FROM sys_params WHERE param_code = 'plugins.fnmusic_gateway.quality')
                )
        ),
        60, 0, NOW(), 0, NOW());

COMMIT;
