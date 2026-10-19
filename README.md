# coldesc

DESC 容器管理插件负责读取当前账号的容器剩余时间，并在启用自动续约后按照设置调用续约接口。

## 功能

- 读取当前账号的 DESC 容器列表
- 显示容器名称、节点、IP、CPU、内存、存储、GPU、系统和备注
- 每秒显示剩余时间倒计时
- 分别按照设置间隔获取容器资料与远端剩余时间
- 在剩余时间低于或等于续约阈值时执行自动续约

## 配置

插件设置保存在插件目录的 config.ini 中的 [coldesc] 配置节：

- DESC 账号和密码
- `container_refresh_interval_seconds`：容器资料获取间隔，默认 259200 秒
- `remaining_refresh_interval_seconds`：远端剩余时间获取间隔，默认 600 秒
- 自动续约开关
- 续约阈值

配置文件包含 DESC 账号密码，请保护该文件。密码输入框不会回显已经保存的密码；更新其他设置时，空密码会继续使用已经保存的密码，清除账号信息需要执行清除操作。

两个获取间隔均使用至少为 15 的整数秒数。页面通过本地保存的到期时间每秒显示倒计时。登录、重新登录和点击“立即获取信息”会获取完整容器资料及剩余时间，续约成功后立即获取新的剩余时间并更新资料。

## 运行方式

插件属于 continuous 类型。后端会在插件启用且账号密码已经配置后启动同步进程，并在插件停用或 Colpilot 退出时结束该进程。

后台请求收到认证失效响应后会重新登录并继续同步。登录失败时，页面提示用户尝试修改账号密码，保留账号表单与“重新登录”按钮。保存账号会重新尝试登录。

## 服务接口

插件使用 DESC 服务的以下接口：

- POST /api/user/validate：验证账号并取得 Bearer token
- GET /api/users：读取用户信息
- GET /api/container/ofuser：读取容器列表
- GET /api/incus/{server}/when/{container}：读取容器剩余时间
- PUT /api/container/renew：执行容器续约

插件页面通过 Colpilot 通用接口保存设置和读取状态：

- GET /api/plugins/coldesc/status
- POST /api/plugins/coldesc/settings：保存设置；`retry_login: true` 重新登录，`refresh_now: true` 立即获取信息
