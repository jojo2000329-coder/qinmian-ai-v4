# ⚛ 勤勉 AI v4 — 辐射级学业规划系统

> **工业美学 × 数字艺术**：赛博朋克风格学业规划 AI，融合放射性尘埃粒子特效、毛玻璃界面和霓虹光晕。

---

## 📋 版本新特性

### v4 新增功能

| 功能 | 说明 |
|------|------|
| 🧠 **长期记忆（知识库）** | 基于关键词权重向量的长期记忆系统，自动存储对话摘要，下次提问时自动召回相关上下文 |
| 💬 **全屏 AI 助手页面** | 赛博朋克风格独立 AI 对话界面，带放射性尘埃粒子动效、毛玻璃卡片、霓虹光晕 |
| 📁 **对话管理** | 新建对话、对话历史查询、对话删除、对话搜索 |
| 🔄 **浮动/全屏协同** | 在工具页面时 AI 助手为右下角浮动窗口；点击「AI 助手」进入全屏沉浸式界面 |
| 🎛 **独立开关** | 大模型开关 + 知识库（长期记忆）开关，可随时启用/禁用 |
| ✨ **粒子动效系统** | Canvas 放射性尘埃粒子效果，支持鼠标交互和对话触发的粒子爆发反馈 |
| 🔐 **多用户登录与数据隔离** | 支持注册、登录、退出；每个账号拥有独立的对话、长期记忆和浏览器偏好 |

### 原有功能保留

- 专业目录浏览与搜索（校区/学院/学科筛选）
- 职业画像反推 4 年课表
- 学分体检与毕业风险预警
- 课程难度多维分析（星级评定）
- 抢课余位监控与模拟捡漏
- 课程冲突智能微调
- 教授研究方向匹配
- 教师列表与职称查询
- SSE 流式聊天
- LangChain Agent + Function Calling
- 多人格对话（勤勉原版/严谨导师/高效规划师/轻松同伴）

---

## 🚀 快速启动

### 环境要求

- Python 3.10+
- 可选：API Key（DeepSeek / OpenAI / 通义千问）

### 安装

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. （可选）配置大模型 API Key
# 编辑 data/llm_config.json
# 或设置环境变量：
#   export OPENAI_API_KEY=sk-xxx
#   export QINMIAN_LLM_PROVIDER=openai
#   export QINMIAN_LLM_MODEL=gpt-5.6-terra
```

### 运行

```bash
python app.py
# 或双击 启动勤勉.cmd
```

浏览器打开 `http://127.0.0.1:8765`

### 每个账号独立配置大模型 API（BYOK）

登录后点击右上角的 **API** 按钮，可以为当前账号单独选择：

- OpenAI
- DeepSeek
- 通义千问（DashScope）
- OpenRouter
- 其他提供 OpenAI 兼容 `/chat/completions` 接口的服务

每个用户可填写自己的 API Base URL、模型名称和 API Key。个人密钥使用
`QINMIAN_SECRET_KEY` 派生的加密密钥后再保存，接口和页面只返回“是否已配置”，
不会回显密钥原文。自定义地址必须使用公开 HTTPS 地址，不能指向本机或内网。
未配置个人 API 时使用平台默认配置；平台也没有可用密钥时自动使用本地工具模式。

首次打开会进入注册/登录页。每个新注册账号都从空白的个人数据空间开始，
不会自动继承 `data/conversations/` 或 `data/knowledge_base/` 中的旧版数据。

登录相关接口：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/auth/me` | 查询当前登录状态 |
| POST | `/api/auth/register` | 注册账号并登录 |
| POST | `/api/auth/login` | 登录 |
| POST | `/api/auth/logout` | 退出 |

除认证接口和 `/health` 外，所有业务 API 都要求有效登录会话。

---

## 🎨 界面说明

### 两种 AI 交互模式

**1. 浮动聊天（工具页面）**
- 在专业浏览、学分体检、课表规划等工具页面时
- AI 助手以右下角浮动窗口形式存在
- 可展开/收起，不影响工具操作

**2. 全屏 AI 助手页面**
- 点击顶部导航栏的「AI 助手」按钮或浮动窗口的 ◆ 按钮进入
- 沉浸式赛博朋克全屏界面
- 左侧：对话列表（新建/搜索/选择/删除）
- 右侧：对话区域（带欢迎快捷入口）
- 底部：输入框 + 状态栏

### 视觉主题

```
配色方案：
  深空黑底    #0a0e17 / #111827
  霓虹青蓝    #00f0ff（主色调，用于强调、边框、光晕）
  霓虹粉紫    #b026ff（辅色调，用于渐变、辐射光晕）
  毛玻璃      rgba(255,255,255,0.04) + blur(16px)

粒子特效：
  - Canvas 渲染的放射性尘埃粒子
  - 粒子从中心向外扩散、漂浮、消散
  - 近距离粒子间自适应连接线
  - 对话触发时产生粒子爆发反馈
  - 周期性光晕脉冲动画
```

---

## 🧠 长期记忆系统

### 工作原理

1. **存储**：每次对话完成后，系统自动将用户问题 + 助手回答转化为关键词权重向量，存入 `data/knowledge_base/records.json`
2. **检索**：下次提问时，系统自动计算问题与历史记录的余弦相似度，召回最相关的 3 条记忆
3. **注入**：召回的记忆以「长期记忆参考」段落注入到 LLM 的系统提示中
4. **开关**：可通过界面中的「💾 记忆」开关随时启用/禁用

### 数据格式

每条记忆记录包含：
- `user_message`: 用户问题
- `assistant_answer`: 助手回答
- `keywords`: 权重最高的 Top-10 关键词
- `weights`: 关键词 TF 权重向量
- `conversation_id`: 所属会话 ID
- `created_at`: 创建时间

### API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/knowledge/status` | 查看知识库状态 |
| POST | `/api/knowledge/toggle` | 切换启用状态 |
| GET | `/api/knowledge/search?q=xxx` | 搜索知识库 |
| GET | `/api/knowledge/records` | 列出所有记录 |
| POST | `/api/knowledge/clear` | 清空当前用户的对话记忆（保留专业知识） |

---

## 💬 对话管理

### API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/conversations` | 列出所有会话 |
| POST | `/api/conversations` | 创建新会话 |
| GET | `/api/conversations/:id` | 获取会话详情 |
| DELETE | `/api/conversations/:id` | 删除会话 |
| POST | `/api/conversations/:id/messages` | 追加消息 |

旧版数据仍保留在 `data/conversations/*.json`，但不会显示给新账号。
登录功能启用后，新数据按账号存储在：

```text
data/user_data/<用户ID>/conversations/
data/user_data/<用户ID>/knowledge_base/records.json
data/user_data/<用户ID>/runtime_state.json
```

账号密码只保存为安全哈希。生产部署应设置随机的 `QINMIAN_SECRET_KEY`，
并持久化 `data/` 或将账号与对话数据迁移到数据库。
其中 `runtime_state.json` 保存该用户独立的抢课监控队列、事件与模拟余位状态。

---

## 🔧 技术架构

```
qinmian/
├── app.py                   # Flask 应用入口 + 所有 API 路由
├── qinmian/
│   ├── agent.py             # 对话代理（含规则引擎 + 记忆系统）
│   ├── analytics.py         # 课程分析、学分检查、冲突解决、教授匹配
│   ├── auth_store.py        # ★ 用户注册、密码哈希、登录数据与目录管理
│   ├── conversation_store.py # ★ 对话持久化存储（新建/查询/删除）
│   ├── data_store.py        # 数据加载与管理
│   ├── knowledge_base.py    # ★ 知识库长期记忆系统
│   ├── llm.py               # LLM 客户端（兼容 OpenAI / DeepSeek / 通义）
│   ├── personas.py          # 多人格定义
│   ├── planner.py           # 职业规划引擎
│   └── tools.py             # Function Calling 工具集
├── static/
│   ├── index.html           # ★ 主页面（含全屏 AI 助手 + 浮动聊天）
│   ├── styles.css           # ★ 赛博朋克主题样式
│   └── app.js               # ★ 前端逻辑（粒子系统 + 对话管理 + 所有交互）
├── data/                    # 各类 JSON 数据文件
│   ├── conversations/       # 旧版对话备份（不自动分配给账号）
│   ├── knowledge_base/      # 旧版知识库备份（不自动分配给账号）
│   ├── users.json           # 账号注册表（仅密码哈希）
│   └── user_data/<用户ID>/  # ★ 每个用户独立的对话、知识库与抢课状态
└── 启动勤勉.cmd             # Windows 启动脚本
```

（★ 标记为 v4 新增或重大修改）

---

## 📝 使用建议

1. **初次使用**：允许页面加载粒子动画，点击「AI 助手」进入全屏界面
2. **启用大模型**：配置 API Key 后，打开界面中的「🧠 大模型」开关
3. **开启长期记忆**：确保「💾 记忆」开关为开启状态，系统会自动存储和召回
4. **多会话管理**：在全屏 AI 页面左侧可以创建多个对话，每个对话独立
5. **随时切换**：点击右上角「⊞」按钮返回工具页面，AI 助手变为浮动窗口

---

## 📦 打包

```bash
# 在项目根目录执行
zip -r qinmian-ai-v4.zip . -x "data/conversations/*" "data/knowledge_base/*" "*.pyc" "__pycache__/*"
```

### Docker 与云部署

项目已提供 `Dockerfile`、`render.yaml` 和 `cloudbase.yaml`，支持部署到 Render、Railway、腾讯云 CloudBase 等容器平台。完整步骤见 [DEPLOYMENT.md](DEPLOYMENT.md)。
