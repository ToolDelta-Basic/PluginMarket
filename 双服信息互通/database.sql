CREATE TABLE IF NOT EXISTS `cross_server_data` (
    `id` INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '消息唯一ID',
    `from_server` VARCHAR(50) NOT NULL COMMENT '发送方服务器标识',
    `to_server` VARCHAR(50) NOT NULL COMMENT '接收方服务器标识',
    `type` VARCHAR(20) NOT NULL DEFAULT 'message' COMMENT '消息类型 (如 message, join, leave)',
    `content` TEXT NOT NULL COMMENT '消息内容',
    `sender_name` VARCHAR(50) NOT NULL DEFAULT 'Unknown' COMMENT '发送者名称',
    `status` TINYINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '读取状态: 0=未读, 1=已读',
    `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '发送时间',
    PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='跨服互通数据中转表';

CREATE INDEX `idx_to_server_status` ON `cross_server_data` (`to_server`, `status`);

CREATE INDEX `idx_status_created` ON `cross_server_data` (`status`, `created_at`);