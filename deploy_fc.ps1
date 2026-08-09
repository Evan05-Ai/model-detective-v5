# 阿里云 FC 部署脚本
# 在部署前安装依赖到本地目录

Write-Host "Installing dependencies..." -ForegroundColor Green
pip install -r requirements.txt -t .

Write-Host "Deploying to Alibaba Cloud FC..." -ForegroundColor Green
s deploy
