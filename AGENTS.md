# AGENTS.md

## 项目范围

`coldesc` 是 Colpilot 的独立插件项目，负责访问 DESC 容器服务，读取容器剩余时间，并执行用户启用的自动续约。

项目根目录的 `AGENTS.md` 规则适用于本项目。开发记录使用项目根目录的 `.learnings` 文件，并遵循 Self Improvement 技能的记录格式。

## 目录规则

- `backend.py` 保存 FastAPI 插件后端和 DESC 服务访问逻辑。
- `manifest.json` 保存插件清单和后端、前端入口。
- `ui` 保存 Vue 页面与样式。
- 用户账号设置统一保存在插件目录的 `config.ini` 中，程序目录只保存程序级配置。

## 接口规则

- 登录使用 `POST /api/user/validate`。
- 用户信息使用 `GET /api/users`。
- 容器列表使用 `GET /api/container/ofuser`。
- 剩余时间使用 `/api/incus/{server}/{container}`。
- 续约使用 `PUT /api/container/renew`。
- 请求收到 401 时重新取得 Bearer token。

## 验证规则

- 修改后运行 Python 编译检查和 Vite 构建。
- 使用真实本地服务检查插件发现、状态读取和启停。
- 不使用 mock 数据、假的账号或假的远程响应。
