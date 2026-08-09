# Model Detective - 阿里云函数计算 FC 部署指南

> 🎯 **目标**：将 Model Detective 部署到阿里云函数计算（国内访问快）

---

## 📋 前置准备

1. **阿里云账号**（已完成实名认证）
   - 网址：https://www.aliyun.com

2. **Serverless Devs 工具**（命令行部署工具）
   - 需要 Node.js 环境

3. **AccessKey**（阿里云 API 访问密钥）

---

## 🚀 部署步骤

### 第一步：安装 Serverless Devs 工具

打开你的本地命令行（PowerShell/CMD），执行：

```bash
# 安装 Serverless Devs
npm install @serverless-devs/s -g

# 验证安装
s -v
```

---

### 第二步：配置阿里云 AccessKey

1. 登录阿里云控制台：https://www.aliyun.com
2. 点击右上角头像 → **"AccessKey 管理"**
3. 创建 AccessKey（如果没有）
4. 记录 **AccessKey ID** 和 **AccessKey Secret**

然后在本地命令行配置：

```bash
# 配置阿里云账号
s config add --AccessKeyID 你的AccessKeyID --AccessKeySecret 你的AccessKeySecret --AccountID 你的阿里云账号ID --alias default

# 查看配置
s config get
```

**获取 AccountID**：
- 登录阿里云控制台
- 点击右上角头像 → **"账号中心"**
- 查看 **"账号 ID"**

---

### 第三步：修改部署配置

我已经为你创建了 `s.yaml` 配置文件，但需要根据你的情况修改：

打开 `s.yaml` 文件，修改以下字段：

```yaml
vars:
  region: cn-hangzhou  # 改成你的地域，如 cn-beijing, cn-shenzhen
```

**可选地域**：
- `cn-hangzhou`（杭州）
- `cn-beijing`（北京）
- `cn-shenzhen`（深圳）
- `cn-shanghai`（上海）
- 其他...

---

### 第四步：部署到阿里云 FC

在项目根目录执行：

```bash
# 进入项目目录
cd d:\Ai工作\model-detective

# 部署
s deploy
```

等待部署完成，你会看到类似输出：

```
✔ Service model-detective-service deployed successfully
✔ Function model-detective deployed successfully
✔ Trigger http-trigger deployed successfully

🚀 访问地址：https://model-detective-xxx.cn-hangzhou.fcapp.run
```

---

### 第五步：访问你的网站

复制输出的网址，在浏览器中打开，即可访问 Model Detective！

---

## 🛠️ 常用操作

### 查看日志

```bash
s logs
```

### 本地调试

```bash
# 本地启动调试服务器
s local start
```

### 更新部署

修改代码后，重新执行：

```bash
s deploy
```

### 删除服务

```bash
s remove
```

---

## 📊 免费额度说明

阿里云函数计算有 **免费额度**：

| 资源类型 | 免费额度 | 说明 |
|----------|----------|------|
| 调用次数 | 100 万次/月 | 展示用途足够 |
| 执行时间 | 40 万 GB-秒/月 | 512MB 内存约 80 万秒 |
| 出网流量 | 1 GB/月 | 注意控制 |

**超出后计费**：
- 调用次数：0.0133 元/万次
- 执行时间：0.000110592 元/GB-秒
- 出网流量：0.8 元/GB

---

## 🛠️ 常见问题排查

### 问题 1：部署失败 "AccessKey invalid"

**解决**：
- 检查 AccessKey ID 和 Secret 是否正确
- 确认账号已完成实名认证
- 重新配置：`s config add`

---

### 问题 2：函数运行超时

**解决**：
- 修改 `s.yaml` 中的 `timeout` 值（默认 60 秒）
- 重新部署：`s deploy`

---

### 问题 3：内存不足

**解决**：
- 修改 `s.yaml` 中的 `memorySize`（默认 512MB）
- 可调整为 1024 或 2048
- 重新部署

---

### 问题 4：静态文件加载慢

**建议**：
- 使用阿里云 OSS + CDN 托管静态文件
- 或调整函数内存到 1024MB 提升性能

---

### 问题 5：SSE 实时推送不工作

**原因**：
- 函数计算的 HTTP 触发器默认不支持长连接
- SSE 需要特殊配置

**解决**：
- 方案 1：改用轮询方式获取进度
- 方案 2：使用阿里云其他产品（如 WebSocket）

---

## 🔧 高级配置

### 自定义域名（可选）

1. 在阿里云控制台 → 函数计算 FC → 你的服务
2. 点击 **"域名管理"**
3. 添加自定义域名
4. 配置 DNS 解析

### 环境变量配置

在 `s.yaml` 中添加：

```yaml
environmentVariables:
  FLASK_ENV: production
  CUSTOM_VAR: your_value
```

---

## ✅ 部署检查清单

- [ ] 阿里云账号已完成实名认证
- [ ] 已创建 AccessKey
- [ ] 已安装 Serverless Devs (`s -v` 有输出)
- [ ] 已配置阿里云账号 (`s config get` 有内容)
- [ ] 已修改 `s.yaml` 中的地域配置
- [ ] 执行 `s deploy` 成功
- [ ] 获得了访问 URL
- [ ] 网站可以正常访问

---

## 🆘 需要帮助？

如果遇到问题：

1. 查看阿里云 FC 官方文档：https://help.aliyun.com/product/50980.html
2. 查看 Serverless Devs 文档：https://docs.serverless-devs.com/
3. 告诉我具体的错误信息，我帮你解决！

---

**祝你部署顺利！** 🎉
