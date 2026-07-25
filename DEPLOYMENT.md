# 勤勉 AI v4 Docker 云部署说明

本项目是 Flask 学业规划 AI，可使用同一个 Docker 镜像部署到腾讯云 CloudBase、Render、Railway 等支持容器的平台。

## 1. 本地 Docker 验证

```bash
docker build -t qinmian-ai-v4 .
docker run --rm -p 8080:8080 \
  -e OPENAI_API_KEY="你的 OpenAI API 密钥" \
  qinmian-ai-v4
```

打开 `http://127.0.0.1:8080`，健康检查地址为 `http://127.0.0.1:8080/health`。

## 2. 上传 GitHub

建议新建仓库 `qinmian-ai-v4`。现有仓库 `ai-text-analyzer` 是另一个 FastAPI 项目，不建议混在一起。

将压缩包解压后的文件上传到仓库根目录。确认 GitHub 中存在：

- `Dockerfile`
- `render.yaml`
- `cloudbase.yaml`
- `app.py`
- `qinmian/`
- `static/`
- `data/`

`data/llm_config.local.json` 不得上传，其中包含本机 API Key。
`_v3_temp/` 是旧版本备份目录，也不要上传。

## 3. Render 在线部署（无需中国大陆实名认证）

1. 登录 `https://render.com`，选择 **New > Blueprint**。
2. 连接刚才的 GitHub 仓库。
3. Render 会自动读取 `render.yaml` 和 `Dockerfile`。
4. 在环境变量中添加：

```text
OPENAI_API_KEY=你的 OpenAI API 密钥
QINMIAN_SECRET_KEY=一个足够长的随机字符串
```

5. 点击部署，等待健康检查通过。
6. 将 Render 生成的 `https://xxx.onrender.com` 地址作为在线服务地址提交。

免费实例可能会在无人访问时休眠，首次打开需要等待一段时间。

## 4. 腾讯云 CloudBase 部署

仓库保留了 `cloudbase.yaml`，端口为 `8080`，健康检查为 `/health`。有可用腾讯云账号时，可按 CloudBase 云托管的 Docker 仓库部署流程使用同一个项目。

## 5. 环境变量

| 名称 | 必填 | 默认值 |
| --- | --- | --- |
| `OPENAI_API_KEY` | 是 | 无 |
| `QINMIAN_LLM_BASE_URL` | 否 | `https://api.openai.com/v1` |
| `QINMIAN_LLM_MODEL` | 否 | `gpt-5.6-terra` |
| `QINMIAN_VISION_MODEL` | 否 | `gpt-5.6-terra` |
| `QINMIAN_SECRET_KEY` | 生产环境必填 | 本地自动生成并写入 `data/.session_secret` |
| `QINMIAN_COOKIE_SECURE` | HTTPS 部署建议设为 `1` | `0` |
| `PORT` | 否 | `8080` |

## 6. 数据持久化说明

专业、课程、教师等基础资料随镜像发布。用户账号、对话记录和运行时记忆默认写入
`data/users.json` 与 `data/user_data/`。免费云实例重建后这些数据可能清空，正式长期使用时
应挂载云硬盘或改用数据库。不要把这些运行时文件提交到 Git 仓库或打入镜像。
