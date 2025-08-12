-- 助手管理端中间件数据库初始化脚本
-- 创建数据库和表结构

-- 使用数据库
USE assistant_management;

-- 客户端连接表
CREATE TABLE IF NOT EXISTS client_connections (
    id CHAR(36) PRIMARY KEY NOT NULL,
    client_id VARCHAR(50) UNIQUE NOT NULL COMMENT '客户端唯一标识',
    doctor_id VARCHAR(50) NOT NULL COMMENT '医生ID',
    doctor_name VARCHAR(100) COMMENT '医生姓名',
    connection_status VARCHAR(20) DEFAULT 'connected' COMMENT '连接状态',
    websocket_id VARCHAR(100) COMMENT 'WebSocket连接ID',
    ip_address VARCHAR(45) COMMENT 'IP地址',
    connected_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '连接时间',
    last_heartbeat DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '最后心跳时间',
    disconnected_at DATETIME COMMENT '断开时间'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='客户端连接表';

-- HIS推送记录表（CDSS消息框架）
CREATE TABLE IF NOT EXISTS his_push_logs (
    id CHAR(36) PRIMARY KEY NOT NULL,
    message_id VARCHAR(50) UNIQUE NOT NULL COMMENT '消息唯一ID',
    system_id VARCHAR(50) NOT NULL COMMENT '系统ID',
    scene_type VARCHAR(20) DEFAULT 'EXAM001' COMMENT '场景类型（检查项目推荐）',
    state INTEGER DEFAULT 0 COMMENT '状态（0:新增,1:更新,-1:撤销）',
    pat_no VARCHAR(50) NOT NULL COMMENT '患者登记号',
    pat_name VARCHAR(100) COMMENT '患者姓名',
    adm_id VARCHAR(50) NOT NULL COMMENT '就诊流水号',
    visit_type VARCHAR(10) COMMENT '就诊类型',
    dept_code VARCHAR(20) COMMENT '科室代码',
    dept_desc VARCHAR(100) COMMENT '科室名称',
    hosp_code VARCHAR(50) COMMENT '院区代码',
    hosp_desc VARCHAR(100) COMMENT '院区名称',
    user_ip VARCHAR(45) COMMENT '客户端IP',
    user_code VARCHAR(50) COMMENT '用户代码（医生ID）',
    user_name VARCHAR(100) COMMENT '用户名称',
    msg_time DATETIME COMMENT 'HIS消息时间',
    remark TEXT COMMENT '备注',
    item_data TEXT COMMENT '场景数据（JSON格式）',
    client_id VARCHAR(50) COMMENT '关联的客户端ID',
    push_status VARCHAR(20) DEFAULT 'success' COMMENT '推送状态',
    error_message TEXT COMMENT '错误信息',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='HIS推送记录表';

-- AI推荐记录表
CREATE TABLE IF NOT EXISTS ai_recommendation_logs (
    id CHAR(36) PRIMARY KEY NOT NULL,
    request_id VARCHAR(50) UNIQUE NOT NULL COMMENT '请求ID',
    client_id VARCHAR(50) NOT NULL COMMENT '客户端ID',
    pat_no VARCHAR(50) NOT NULL COMMENT '患者登记号（来自CDSS）',
    adm_id VARCHAR(50) NOT NULL COMMENT '就诊流水号（来自CDSS）',
    user_code VARCHAR(50) NOT NULL COMMENT '用户代码（医生ID，来自CDSS）',
    dept_code VARCHAR(20) COMMENT '科室代码（来自CDSS）',
    message_id VARCHAR(50) COMMENT '关联CDSS消息ID',
    his_push_log_id CHAR(36) COMMENT '关联HIS推送记录ID',
    ai_request_data TEXT NOT NULL COMMENT 'JSON格式的AI服务请求数据',
    ai_response_data TEXT COMMENT 'JSON格式的AI服务完整响应',
    recommendations TEXT COMMENT 'JSON格式的最终推荐结果',
    processing_time DECIMAL(5,2) COMMENT '处理时间（秒）',
    ai_service_url VARCHAR(200) COMMENT 'AI服务地址',
    session_id VARCHAR(50) COMMENT 'AI服务会话ID',
    status VARCHAR(20) DEFAULT 'success' COMMENT '处理状态',
    error_message TEXT COMMENT '错误信息',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='AI推荐记录表';

-- 系统日志表
CREATE TABLE IF NOT EXISTS system_logs (
    id CHAR(36) PRIMARY KEY NOT NULL,
    log_level VARCHAR(10) NOT NULL COMMENT '日志级别',
    module VARCHAR(50) NOT NULL COMMENT '模块名称',
    operation VARCHAR(100) NOT NULL COMMENT '操作描述',
    client_id VARCHAR(50) COMMENT '客户端ID',
    request_id VARCHAR(50) COMMENT '请求ID',
    push_id VARCHAR(50) COMMENT '推送ID',
    message TEXT NOT NULL COMMENT '日志消息',
    details TEXT COMMENT 'JSON格式的详细信息',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='系统日志表';

-- 创建索引
CREATE INDEX idx_client_connections_client_id ON client_connections(client_id);
CREATE INDEX idx_client_connections_doctor_id ON client_connections(doctor_id);
CREATE INDEX idx_client_connections_ip_address ON client_connections(ip_address);

CREATE INDEX idx_his_push_logs_message_id ON his_push_logs(message_id);
CREATE INDEX idx_his_push_logs_pat_no ON his_push_logs(pat_no);
CREATE INDEX idx_his_push_logs_adm_id ON his_push_logs(adm_id);
CREATE INDEX idx_his_push_logs_user_code ON his_push_logs(user_code);
CREATE INDEX idx_his_push_logs_created_at ON his_push_logs(created_at);

CREATE INDEX idx_ai_recommendation_logs_request_id ON ai_recommendation_logs(request_id);
CREATE INDEX idx_ai_recommendation_logs_client_id ON ai_recommendation_logs(client_id);
CREATE INDEX idx_ai_recommendation_logs_pat_no ON ai_recommendation_logs(pat_no);
CREATE INDEX idx_ai_recommendation_logs_created_at ON ai_recommendation_logs(created_at);

CREATE INDEX idx_system_logs_module ON system_logs(module);
CREATE INDEX idx_system_logs_log_level ON system_logs(log_level);
CREATE INDEX idx_system_logs_created_at ON system_logs(created_at);

-- 插入初始化数据（可选）
INSERT INTO system_logs (log_level, module, operation, message, details) 
VALUES ('INFO', 'database', 'init', '数据库初始化完成', '{"timestamp": "2024-12-19", "version": "1.0.0"}');

-- 设置权限（如果需要）
-- GRANT ALL PRIVILEGES ON assistant_management.* TO 'assistant_user'@'%';
-- FLUSH PRIVILEGES;