# 助手管理端中间件 - MVP阶段

## 📋 项目概述

助手管理端中间件是医疗助手系统的核心组件，作为HIS系统、助手客户端和AI服务之间的桥梁，实现患者病历信息的实时推送和AI检查项目推荐功能。

## 🎯 MVP阶段目标

本项目实现5个核心功能：

1. **HIS接口接收** - 接收HIS系统推送的患者病历信息
2. **WebSocket连接管理** - 管理客户端实时连接
3. **AI服务代理** - 为客户端提供AI推荐服务代理
4. **AI接口调用** - 调用外部AI推荐服务
5. **调用链日志** - 完整的业务链路日志记录

## 🏗️ 技术架构

- **后端框架**: Python 3.11 + FastAPI
- **数据库**: MySQL + SQLAlchemy ORM
- **实时通信**: WebSocket
- **HTTP客户端**: httpx
- **日志系统**: loguru
- **数据验证**: Pydantic

## 📁 项目结构

```
rimag-assistant-platform/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI应用入口
│   ├── core/                   # 核心配置
│   │   ├── config.py          # 配置管理
│   │   ├── database.py        # 数据库连接
│   │   └── logging.py         # 日志配置
│   ├── models/                 # 数据库模型
│   │   └── database_models.py # SQLAlchemy模型
│   ├── schemas/                # Pydantic模型
│   │   ├── his_schemas.py     # HIS接口模型
│   │   ├── websocket_schemas.py # WebSocket消息模型
│   │   └── ai_schemas.py      # AI服务模型
│   ├── api/                    # API路由
│   │   └── routes/
│   │       ├── his_push.py    # HIS推送接口
│   │       ├── ai_proxy.py    # AI代理接口
│   │       └── websocket_manager.py # WebSocket路由
│   └── services/               # 业务服务
│       ├── his_service.py     # HIS业务逻辑
│       ├── ai_service.py      # AI服务调用
│       └── websocket_service.py # WebSocket管理
├── logs/                       # 日志文件目录
├── pyproject.toml             # 项目配置
└── README.md                  # 项目说明
```

## 🚀 快速开始

### 1. 环境准备

```bash
# 确保已安装Python 3.11+
python --version

# 安装uv包管理器（如果未安装）
pip install uv
```

### 2. 安装依赖

```bash
# 进入项目目录
cd rimag-assistant-platform

# 安装项目依赖
uv sync
```

### 3. 数据库配置

```bash
# 创建MySQL数据库
mysql -u root -p
CREATE DATABASE assistant_management CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### 4. 环境配置

```bash
# 复制环境配置文件
cp env.example .env

# 编辑配置文件，修改数据库连接信息
vim .env
```

### 5. 启动服务

```bash
# 开发模式启动
uv run python -m app.main

# 或使用uvicorn直接启动
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## 📡 API接口

### HIS推送接口

```http
POST /api/CHKR01/rest/
Content-Type: application/json
hospital_id: 400688609-7
service_id: CHKR01
visit_type: 01
send_sys_id: HIS_SYS_001

{
  "systemId": "S031",
  "sceneType": "EXAM001",
  "state": 0,
  "patNo": "12345678",
  "patName": "张三",
  "admId": "61234567",
  "visitType": "01",
  "deptCode": "12301",
  "deptDesc": "消化内科",
  "userIP": "10.10.10.25",
  "userCode": "123-001",
  "userName": "李四",
  "msgTime": "2024-12-19 10:30:00",
  "itemData": {
    "patientAge": "45",
    "patientSex": "男",
    "clinicInfo": "上腹部疼痛3天",
    "abstractHistory": "患者3天前开始出现上腹部疼痛..."
  }
}
```

### AI代理接口

```http
POST /api/ai/recommend
Content-Type: application/json

{
  "client_id": "client_12301_001",
  "doctor_id": "123-001",
  "request_id": "req_20241219_001",
  "patient_id": "12345678",
  "visit_id": "61234567"
}
```

### WebSocket连接

```javascript
// 客户端连接
const ws = new WebSocket('ws://localhost:8000/ws/client/client_12301_001');

// 消息格式
{
  "type": "patient_data",
  "id": "msg_001",
  "timestamp": "2024-12-19T10:30:00Z",
  "data": {
    "patNo": "12345678",
    "patName": "张三",
    // ... 其他患者信息
  }
}
```

## 🗄️ 数据库表结构

- **client_connections** - 客户端连接记录
- **his_push_logs** - HIS推送日志（CDSS消息）
- **ai_recommendation_logs** - AI推荐记录
- **system_logs** - 系统操作日志

## 📊 监控和日志

### 健康检查
```http
GET /health
```

### 连接状态查询
```http
GET /ws/clients
```

### 日志文件
- 控制台输出：彩色格式，便于开发调试
- 文件输出：`logs/assistant_management.log`
- 日志轮转：100MB自动轮转，保留30天

## 🔧 配置说明

主要配置项（`.env`文件）：

- `MYSQL_*` - MySQL数据库连接配置
- `AI_SERVICE_*` - 外部AI服务配置
- `WS_*` - WebSocket相关配置
- `LOG_*` - 日志系统配置

## 🚨 故障排除

### 常见问题

1. **数据库连接失败**
   - 检查MySQL服务是否启动
   - 验证数据库连接参数
   - 确认数据库用户权限

2. **WebSocket连接异常**
   - 检查防火墙设置
   - 验证client_id格式
   - 查看连接日志

3. **AI服务调用超时**
   - 检查网络连通性
   - 验证AI服务地址
   - 调整超时配置

## 📝 开发指南

### 添加新的API接口
1. 在`app/schemas/`中定义数据模型
2. 在`app/api/routes/`中创建路由文件
3. 在`app/services/`中实现业务逻辑
4. 在`app/main.py`中注册路由

### 扩展WebSocket消息类型
1. 在`app/schemas/websocket_schemas.py`中定义新消息类型
2. 在`app/services/websocket_service.py`中实现处理逻辑
3. 更新路由处理函数

## 📄 许可证

本项目为内部开发项目，仅供团队内部使用。

## 👥 贡献者

- 架构设计团队
- MVP开发团队

---

*文档版本：v1.0*  
*最后更新：2024-12-19*
