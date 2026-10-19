# coldesc

DESC 容器管理插件负责读取当前账号的容器剩余时间，并在启用自动续约后按照设置调用续约接口。

## 功能

- 读取当前账号的 DESC 容器列表
- 显示每个容器的剩余时间和同步状态
- 按照设置周期同步容器状态
- 在剩余时间低于或等于续约阈值时执行自动续约

## 配置

插件设置保存在插件目录的 config.ini 中的 [coldesc] 配置节：

- DESC 账号和密码
- 容器同步周期，最小值为 15 秒
- 自动续约开关
- 续约阈值

配置文件包含 DESC 账号密码，请保护该文件。密码输入框不会回显已经保存的密码；更新其他设置时，空密码会继续使用已经保存的密码，清除账号信息需要执行清除操作。

## 运行方式

插件属于 continuous 类型。后端会在插件启用且账号密码已经配置后启动同步进程，并在插件停用或 Colpilot 退出时结束该进程。

后台请求收到认证失效响应后会重新登录并继续同步。自动续约请求成功后，插件会重新读取对应容器的剩余时间；认证失败或接口数据格式错误会显示在插件状态中。

## 服务接口

插件使用 DESC 服务的以下接口：

- POST /api/user/validate：验证账号并取得 Bearer token
- GET /api/users：读取用户信息
- GET /api/container/ofuser：读取容器列表
- /api/incus/{server}/{container}：读取容器剩余时间
- PUT /api/container/renew：执行容器续约

插件页面通过 Colpilot 通用接口保存设置和读取状态：

- GET /api/plugins/coldesc/status
- POST /api/plugins/coldesc/settings

# colpilot.coldesc
