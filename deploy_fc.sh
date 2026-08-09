#!/bin/bash
# 阿里云 FC 部署脚本
# 在部署前安装依赖到本地目录

echo "Installing dependencies..."
pip install -r requirements.txt -t .

echo "Deploying to Alibaba Cloud FC..."
s deploy
