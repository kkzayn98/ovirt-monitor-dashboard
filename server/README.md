# 采集服务

在 nobug (78) 上以 `kangzijin` 的 SSH 私钥并行登录集群主机，采集在线用户与 Top 进程。

## 配置

编辑 [`config.yaml`](config.yaml)：

- `ssh_user` / `ssh_key`
- `cidrs`：扫描网段
- `hosts`：可选显式主机列表（可与 CIDR 合并）
- `concurrency` / 超时 / `refresh_interval_seconds`

## 启动

```bash
cd server
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8787
```

确保运行用户能读取 `ssh_key`（当前默认 `/home/kangzijin/.ssh/id_ed25519`）。

## API

- `GET /api/stats`
- `GET /api/users`
- `GET /api/users/{username}/processes?vmIp=`
- `GET /api/hosts`
- `GET /api/meta`
- `POST /api/refresh` — 触发全量重采

## 日志

每次全量刷新会覆盖写入 `logs/ssh_failed_hosts.log`：列出 **SSH 端口可达但认证/采集失败** 的 IP（不含整段扫描中端口关闭的地址），便于确认哪些机器需要纳入监控或修复 SSSD。
