# Raina 集群监控大屏

实时监控 oVirt VM 上用户活动与资源占用。本机（nobug / 78）通过 `kangzijin` SSH 密钥并行采集 IPA 主机。

## 功能

- 集群概览：在线用户、可达 VM、CPU/内存均值
- 在线用户列表：搜索、按 CPU/内存/登录时长排序
- 用户详情：Top 5 占用进程
- 资源预警：主机/用户 CPU·内存超阈值大屏提示，标明建议联系的用户；日志 `server/logs/alerts.log`，可选 webhook 通知 IT
- 按 **hostname** 去重展示 VM（双网卡双 IP 不计重复）
- SSH 异常主机 IP 写入 [`server/logs/ssh_failed_hosts.log`](server/logs/ssh_failed_hosts.log) 便于确认是否需监控
- 前端约 30 秒检查快照更新；后端约 120 秒全量 SSH 重采（可在 `server/config.yaml` 调整）
- 用户 CPU/内存列：该用户占所在主机整体资源的比例

## 技术栈

- 前端：React 18 + TypeScript + Vite + Tailwind + Zustand
- 后端：FastAPI + asyncssh

## 密钥与密码

- 默认：`kangzijin` + SSH 私钥
- `tbn00`–`tbn18`：`root` + 密码（写在 [`server/secrets.yaml`](server/secrets.yaml)，已 gitignore）
- 密码/账号分组在 [`server/config.yaml`](server/config.yaml) 的 `auth_profiles`

## 钉钉预警机器人（加签）

1. 钉钉企业内部群 → 群设置 → 机器人 → 添加「自定义」机器人，安全设置选 **加签**
2. 将 Webhook 与 SEC 写入 `server/secrets.yaml`：

```yaml
dingtalk_webhook_url: "https://oapi.dingtalk.com/robot/send?access_token=..."
dingtalk_secret: "SEC..."
```

3. 重启采集服务后，严重告警会 POST 到群（带 timestamp/sign）。同一告警默认 30 分钟冷却。
4. 日志仍写在 `server/logs/alerts.log` 与 `alerts_it_brief.txt`。

### 1. 构建前端并启动（推荐，单端口，避免 Vite 代理 502）

```bash
export PATH="$PWD/.tools/node/bin:$PATH"   # 若系统 Node 过旧
npm install
npm run build

cd server
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8787
```

服务监听 **`0.0.0.0:8787`**（本机三块网卡均可访问）。出口侧请走 **`192.168.10.78:8787`**，由 `192.168.10.51` 上的 nginx 反代对外；示例配置见 [`deploy/nginx-monitor.conf.example`](deploy/nginx-monitor.conf.example)。

内网直连也可：`http://192.168.15.78:8787` 或 `http://192.168.10.78:8787`。

编辑 [`server/config.yaml`](server/config.yaml) 配置网段与密钥路径。默认扫描 `192.168.15.0/24` 与 `192.168.10.0/24`。

### 2. 开发模式（可选，Vite :3000）

```bash
# 终端 1
cd server && source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8787

# 终端 2
export PATH="$PWD/.tools/node/bin:$PATH"
npm run dev -- --host 0.0.0.0 --port 3000
```

访问 http://localhost:3000 。若出现 502，请改用上面的单端口方式（`:8787`）。

## 项目结构

```
ovirt-monitor-dashboard/
├── server/                 # FastAPI SSH 采集
│   ├── app/
│   ├── config.yaml
│   └── requirements.txt
├── src/
│   ├── components/
│   ├── hooks/
│   ├── services/api.ts
│   ├── store/
│   └── utils/mockData.ts
└── package.json
```

## 许可证

MIT
