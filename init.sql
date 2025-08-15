-- 助手管理端中间件数据库初始化脚本（对齐 docs/12-数据库表设计.md）
-- 使用数据库
USE assistant_management;

-- 1) 系统字典表
CREATE TABLE IF NOT EXISTS sys_dict (
	id CHAR(36) PRIMARY KEY,
	dict_type VARCHAR(50) NOT NULL,
	dict_key VARCHAR(50) NOT NULL,
	dict_value VARCHAR(100) NOT NULL,
	description TEXT,
	sort_order INT DEFAULT NULL,
	enabled BOOLEAN NOT NULL DEFAULT TRUE,
	create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
	update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
	UNIQUE KEY uk_type_key (dict_type, dict_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='系统字典表';

-- 2) 服务治理：服务与接口
CREATE TABLE IF NOT EXISTS services (
	id CHAR(36) PRIMARY KEY,
	name VARCHAR(100) NOT NULL,
	type VARCHAR(20) NOT NULL,
	base_path VARCHAR(200) NOT NULL,
	protocol VARCHAR(10) NOT NULL,
	enabled BOOLEAN NOT NULL DEFAULT TRUE,
	description TEXT,
	create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
	update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
	KEY idx_service_type (type),
	KEY idx_service_enabled (enabled)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='服务定义表';

CREATE TABLE IF NOT EXISTS service_interface (
	id CHAR(36) PRIMARY KEY,
	service_id CHAR(36) NOT NULL,
	name VARCHAR(100) NOT NULL,
	path VARCHAR(200) NOT NULL,
	method VARCHAR(10) NOT NULL,
	target_url VARCHAR(500) DEFAULT NULL,
	timeout_seconds INT NOT NULL DEFAULT 5,
	enabled BOOLEAN NOT NULL DEFAULT TRUE,
	request_sample JSON DEFAULT NULL,
	response_schema JSON DEFAULT NULL,
	create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
	update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
	KEY idx_interface_service (service_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='接口注册表';

-- 3) 客户端管理
CREATE TABLE IF NOT EXISTS client_info (
	client_id CHAR(36) PRIMARY KEY,
	hospital_id VARCHAR(64) DEFAULT NULL,
	department VARCHAR(50) DEFAULT NULL,
	ip_address VARCHAR(45) DEFAULT NULL,
	client_version VARCHAR(20) DEFAULT NULL,
	enabled BOOLEAN NOT NULL DEFAULT TRUE,
	connected BOOLEAN NOT NULL DEFAULT FALSE,
	connected_at DATETIME DEFAULT NULL,
	last_active DATETIME DEFAULT NULL,
	create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
	update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
	KEY idx_client_hospital (hospital_id),
	KEY idx_client_connected (connected),
	KEY idx_client_last_active (last_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='客户端信息表';

-- 4) 权限配置（RBAC）
CREATE TABLE IF NOT EXISTS role_info (
	role_id CHAR(36) PRIMARY KEY,
	role_name VARCHAR(50) NOT NULL,
	description TEXT DEFAULT NULL,
	type VARCHAR(20) DEFAULT 'DEPT',
	enabled BOOLEAN NOT NULL DEFAULT TRUE,
	create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
	update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
	KEY idx_role_name (role_name),
	KEY idx_role_type (type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='权限组表';

CREATE TABLE IF NOT EXISTS role_service_acl (
	id CHAR(36) PRIMARY KEY,
	role_id CHAR(36) NOT NULL,
	service_id CHAR(36) NOT NULL,
	create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
	UNIQUE KEY uk_role_service (role_id, service_id),
	KEY idx_role_service_service (service_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='权限组-服务授权表';

CREATE TABLE IF NOT EXISTS client_role_binding (
	id CHAR(36) PRIMARY KEY,
	client_id CHAR(36) NOT NULL,
	role_id CHAR(36) NOT NULL,
	create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
	UNIQUE KEY uk_client_role (client_id, role_id),
	KEY idx_client_role_role (role_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='客户端-权限组绑定表';

-- 5) 调用链追踪
CREATE TABLE IF NOT EXISTS trace_record (
	trace_id CHAR(36) PRIMARY KEY,
	patient_id VARCHAR(64) DEFAULT NULL,
	hospital_id VARCHAR(64) DEFAULT NULL,
	start_time DATETIME NOT NULL,
	end_time DATETIME DEFAULT NULL,
	status VARCHAR(20) NOT NULL,
	total_duration_ms INT NOT NULL,
	create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
	KEY idx_trace_patient (patient_id),
	KEY idx_trace_time (start_time),
	KEY idx_trace_status (status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='调用链主表';

CREATE TABLE IF NOT EXISTS span_record (
	span_id CHAR(36) PRIMARY KEY,
	trace_id CHAR(36) NOT NULL,
	parent_span_id CHAR(36) DEFAULT NULL,
	service_name VARCHAR(50) NOT NULL,
	span_name VARCHAR(100) NOT NULL,
	start_time DATETIME NOT NULL,
	end_time DATETIME NOT NULL,
	duration_ms INT NOT NULL,
	status VARCHAR(20) NOT NULL,
	request_data JSON DEFAULT NULL,
	response_data JSON DEFAULT NULL,
	error_message TEXT DEFAULT NULL,
	client_id CHAR(36) DEFAULT NULL,
	api_path VARCHAR(200) DEFAULT NULL,
	create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
	KEY idx_span_trace (trace_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='调用片段表';

-- 6) 会话管理
CREATE TABLE IF NOT EXISTS ai_session (
	id CHAR(36) PRIMARY KEY,
	session_key VARCHAR(80) NOT NULL,
	patient_id VARCHAR(64) NOT NULL,
	client_id CHAR(36) NOT NULL,
	hospital_id VARCHAR(64) DEFAULT NULL,
	session_date DATE NOT NULL,
	create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
	update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
	status VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
	UNIQUE KEY uk_patient_date (patient_id, session_date),
	UNIQUE KEY uk_session_key (session_key),
	KEY idx_session_patient (patient_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='会话主表';

CREATE TABLE IF NOT EXISTS ai_session_record (
	record_id CHAR(36) PRIMARY KEY,
	session_id CHAR(36) NOT NULL,
	trace_id CHAR(36) DEFAULT NULL,
	service_name VARCHAR(50) NOT NULL,
	request_time DATETIME NOT NULL,
	request_data JSON DEFAULT NULL,
	response_data JSON DEFAULT NULL,
	duration_ms INT DEFAULT NULL,
	metadata JSON DEFAULT NULL,
	create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
	KEY idx_record_session (session_id),
	KEY idx_record_trace (trace_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='会话记录表';

-- 7) 服务调用明细
CREATE TABLE IF NOT EXISTS service_calls (
	id CHAR(36) PRIMARY KEY,
	client_id CHAR(36) NOT NULL,
	service_id CHAR(36) NOT NULL,
	started_at DATETIME NOT NULL,
	ended_at DATETIME DEFAULT NULL,
	status VARCHAR(20) NOT NULL,
	latency_ms INT DEFAULT NULL,
	req_summary JSON DEFAULT NULL,
	resp_summary JSON DEFAULT NULL,
	create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
	KEY idx_client_time (client_id, started_at),
	KEY idx_service_time (service_id, started_at),
	KEY idx_status_time (status, started_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='服务调用明细';

-- 8) 字典初始化数据（可选）
INSERT INTO sys_dict (id, dict_type, dict_key, dict_value, description, sort_order, enabled) VALUES
('00000000-0000-0000-0000-000000000001', 'service_type', 'HIS_SERVICE', 'HIS服务', '由助手管理服务端提供给HIS调用的服务', 1, TRUE),
('00000000-0000-0000-0000-000000000002', 'service_type', 'MODEL_SERVICE', '模型服务', '助手管理服务端代理的AI模型服务', 2, TRUE)
ON DUPLICATE KEY UPDATE dict_value=VALUES(dict_value);

INSERT INTO sys_dict (id, dict_type, dict_key, dict_value, description, sort_order, enabled) VALUES
('00000000-0000-0000-0000-000000000003', 'protocol_type', 'HTTP', 'HTTP', 'HTTP协议', 1, TRUE),
('00000000-0000-0000-0000-000000000004', 'protocol_type', 'WEBSOCKET', 'WebSocket', 'WebSocket协议', 2, TRUE)
ON DUPLICATE KEY UPDATE dict_value=VALUES(dict_value);

INSERT INTO sys_dict (id, dict_type, dict_key, dict_value, description, sort_order, enabled) VALUES
('00000000-0000-0000-0000-000000000005', 'role_type', 'DEPT', '科室', '按医院科室划分的权限组', 1, TRUE),
('00000000-0000-0000-0000-000000000006', 'role_type', 'CUSTOM', '自定义组', '管理员自定义的权限组合', 2, TRUE)
ON DUPLICATE KEY UPDATE dict_value=VALUES(dict_value);

INSERT INTO sys_dict (id, dict_type, dict_key, dict_value, description, sort_order, enabled) VALUES
('00000000-0000-0000-0000-000000000007', 'trace_status', 'SUCCESS', '成功', '调用链执行成功', 1, TRUE),
('00000000-0000-0000-0000-000000000008', 'trace_status', 'FAILED', '失败', '调用链执行失败', 2, TRUE),
('00000000-0000-0000-0000-000000000009', 'trace_status', 'TIMEOUT', '超时', '调用链超时', 3, TRUE)
ON DUPLICATE KEY UPDATE dict_value=VALUES(dict_value);

INSERT INTO sys_dict (id, dict_type, dict_key, dict_value, description, sort_order, enabled) VALUES
('00000000-0000-0000-0000-000000000010', 'session_status', 'ACTIVE', '活跃', '会话正在进行中', 1, TRUE)
ON DUPLICATE KEY UPDATE dict_value=VALUES(dict_value);

INSERT INTO sys_dict (id, dict_type, dict_key, dict_value, description, sort_order, enabled) VALUES
('00000000-0000-0000-0000-000000000011', 'client_status', 'ONLINE', '在线', '客户端已连接', 1, TRUE),
('00000000-0000-0000-0000-000000000012', 'client_status', 'OFFLINE', '离线', '客户端未连接', 2, TRUE)
ON DUPLICATE KEY UPDATE dict_value=VALUES(dict_value);

INSERT INTO sys_dict (id, dict_type, dict_key, dict_value, description, sort_order, enabled) VALUES
('00000000-0000-0000-0000-000000000013', 'boolean', 'TRUE', '是', '布尔值：是', 1, TRUE),
('00000000-0000-0000-0000-000000000014', 'boolean', 'FALSE', '否', '布尔值：否', 2, TRUE)
ON DUPLICATE KEY UPDATE dict_value=VALUES(dict_value);

INSERT INTO sys_dict (id, dict_type, dict_key, dict_value, description, sort_order, enabled) VALUES
('00000000-0000-0000-0000-000000000015', 'method_type', 'GET', 'GET', 'HTTP GET 方法', 1, TRUE),
('00000000-0000-0000-0000-000000000016', 'method_type', 'POST', 'POST', 'HTTP POST 方法', 2, TRUE),
('00000000-0000-0000-0000-000000000017', 'method_type', 'PUT', 'PUT', 'HTTP PUT 方法', 3, TRUE),
('00000000-0000-0000-0000-000000000018', 'method_type', 'DELETE', 'DELETE', 'HTTP DELETE 方法', 4, TRUE)
ON DUPLICATE KEY UPDATE dict_value=VALUES(dict_value);