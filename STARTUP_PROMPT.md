# Model Detective 满血启动提示词

## 项目基本信息
- **项目名称**: Model Detective v5.1 Cosmic Galaxy
- **项目路径**: `d:/Ai工作/model-detective`
- **GitHub**: https://github.com/Evan05-Ai/model-detective-v5
- **技术栈**: Python Flask 3.1.3 + HTML/CSS/JS

## 当前部署状态

### 1. PythonAnywhere（已上线）
- **网址**: https://Evan05Ai.pythonanywhere.com
- **账号**: Beginner（免费）
- **限制**: 
  - CPU: 100秒/天
  - 支持 Quick 检测（完美）
  - 支持 Standard 检测（每天1-2次）
  - 不支持 Full 检测（CPU超限）
  - 需每月续命（点击"Run until 1 month from today"）

### 2. 阿里云 FC（部署失败）
- 尝试多次 Flask 适配均失败
- 错误: 返回格式问题，浏览器下载文件而非显示网页
- 已放弃此方案

### 3. 阿里云 ECS（待部署）
- 用户正在申请试用资格
- 预计费用: 20-30元/月
- 将支持完整功能（Quick/Standard/Full）

## 关键文件位置
```
d:/Ai工作/model-detective/
├── web/app.py                 # Flask主应用
├── web/static/                # 静态文件(CSS/JS)
├── web/templates/             # HTML模板
├── flask_app.py               # PythonAnywhere入口
├── aliyun_fc_app.py           # 阿里云FC适配器（未成功）
├── s.yaml                     # 阿里云FC部署配置
├── DEPLOY_PYTHONANYWHERE.md   # PythonAnywhere部署指南
├── DEPLOY_ALIYUN_FC.md        # 阿里云FC部署指南
├── requirements.txt           # Python依赖
└── run_web.py                 # 本地启动脚本
```

## 启动命令
```bash
# 本地开发
.venv\Scripts\python.exe run_web.py

# PythonAnywhere已部署，直接访问网址
```

## 用户当前需求
1. 使用 PythonAnywhere 进行演示（Quick/Standard模式）
2. 待申请阿里云ECS试用资格后部署完整功能
3. 需要支持Standard/Full检测的完整方案

## 下一步行动
等待用户获取阿里云ECS试用资格，协助部署完整功能方案。

## 重要提醒
- PythonAnywhere 每月需手动续命
- Standard检测每天限制1-2次
- ECS部署后将解决所有限制
