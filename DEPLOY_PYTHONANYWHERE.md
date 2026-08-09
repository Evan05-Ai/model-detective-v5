# Model Detective - PythonAnywhere 部署指南

> 🎯 **目标**：零成本、零绑卡部署 Model Detective 到 PythonAnywhere

---

## 📋 前置准备

1. 一个 **PythonAnywhere 账号**（免费注册）
   - 网址：https://www.pythonanywhere.com
   - 点击 "Start running Python online in less than a minute"
   - 填写用户名、邮箱、密码即可

2. 确保你的代码已推送到 **GitHub**

---

## 🚀 部署步骤（跟着做就行）

### 第一步：登录 PythonAnywhere

1. 打开 https://www.pythonanywhere.com
2. 点击 **"Log in"** 登录你的账号

---

### 第二步：打开 Bash 控制台

1. 登录后点击顶部菜单 **"Consoles"**
2. 点击 **"Bash"** 打开一个命令行窗口

---

### 第三步：克隆你的代码

在 Bash 控制台中执行以下命令：

```bash
# 进入你的 home 目录（通常已经在）
cd ~

# 克隆你的 GitHub 仓库（替换为你的仓库地址）
git clone https://github.com/evan05-ai/model-detective.git

# 进入项目目录
cd model-detective
```

---

### 第四步：创建虚拟环境并安装依赖

```bash
# 创建 Python 3.10 虚拟环境
mkvirtualenv --python=/usr/bin/python3.10 model-detective-env

# 如果提示虚拟环境已存在，直接激活
# workon model-detective-env

# 安装依赖
pip install -r requirements.txt
```

---

### 第五步：配置 Web 应用

1. 点击顶部菜单 **"Web"**
2. 点击 **"Add a new web app"**
3. 选择 **"Manual configuration"**（手动配置）
4. 选择 **"Python 3.10"**
5. 点击 **"Next"**

---

### 第六步：配置 Web 应用路径

在 Web 配置页面，填写以下信息：

| 配置项 | 填写内容 |
|--------|----------|
| **Source code** | `/home/你的用户名/model-detective` |
| **Working directory** | `/home/你的用户名/model-detective` |
| **WSGI configuration file** | 点击链接编辑 |

#### 编辑 WSGI 配置文件：

点击 WSGI configuration file 的链接，删除原有内容，粘贴以下代码：

```python
import sys
import os

# 添加项目路径
path = '/home/你的用户名/model-detective'
if path not in sys.path:
    sys.path.insert(0, path)

# 设置环境变量
os.environ['FLASK_ENV'] = 'production'

# 导入 Flask 应用
from flask_app import application
```

**注意**：将 `你的用户名` 替换为你的 PythonAnywhere 用户名！

---

### 第七步：配置静态文件（可选但推荐）

在 Web 配置页面下方，找到 **"Static files"** 部分：

| URL | Directory |
|-----|-----------|
| `/static/` | `/home/你的用户名/model-detective/web/static` |

点击 **"Enter URL"** 和 **"Enter path"** 添加上述配置。

---

### 第八步：重启 Web 应用

1. 返回 Web 配置页面顶部
2. 点击 **"Reload"** 按钮（大绿色按钮）
3. 等待几秒钟

---

### 第九步：访问你的网站

1. 页面顶部会显示你的网址：
   ```
   https://你的用户名.pythonanywhere.com
   ```
2. 点击链接访问，应该能看到 Model Detective 首页！

---

## 🛠️ 常见问题排查

### 问题 1："Something went wrong" 错误页面

**排查步骤**：

1. 查看错误日志：
   - 点击 Web 配置页面的 **"Error log"** 链接
   - 查看具体错误信息

2. 常见原因：
   - 路径配置错误 → 检查 WSGI 文件中的路径
   - 依赖未安装 → 重新运行 `pip install -r requirements.txt`
   - 虚拟环境未激活 → 确保使用 `workon model-detective-env`

---

### 问题 2：静态文件（CSS/JS）加载失败

**解决**：
- 确保已配置 Static files（见第七步）
- 检查路径是否正确

---

### 问题 3：API 请求报错

**排查**：
- 查看 **"Server log"** 了解后端错误
- 确保所有依赖已正确安装

---

### 问题 4：代码更新后未生效

**解决**：
1. 在 Bash 中拉取最新代码：
   ```bash
   cd ~/model-detective
   git pull origin master
   ```
2. 点击 Web 配置页面的 **"Reload"** 重启应用

---

## 📊 免费版限制说明

| 限制项 | 额度 | 说明 |
|--------|------|------|
 每日 CPU 时间 | 100 秒 | 展示用途足够 |
| 每日网络请求 | 100,000 次 | 完全够用 |
| 磁盘空间 | 512 MB | 代码足够存放 |
| 强制休眠 | 每天 3 小时 | 凌晨时段，影响较小 |
| 自定义域名 | ❌ 不支持 | 使用默认域名 |

---

## ✅ 部署检查清单

- [ ] PythonAnywhere 账号已注册
- [ ] 代码已克隆到 `/home/用户名/model-detective`
- [ ] 虚拟环境已创建并激活
- [ ] 依赖已安装 (`requirements.txt`)
- [ ] Web 应用已创建（Manual configuration）
- [ ] WSGI 文件已配置正确
- [ ] 静态文件路径已配置（可选）
- [ ] 点击 Reload 重启应用
- [ ] 网站可以正常访问

---

## 🆘 需要帮助？

如果在部署过程中遇到问题：

1. 查看 PythonAnywhere 官方文档：https://help.pythonanywhere.com/
2. 检查错误日志定位问题
3. 告诉我具体的错误信息，我帮你解决！

---

**祝你部署顺利！** 🎉
