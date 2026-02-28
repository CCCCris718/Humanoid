# 推送到 GitHub 步骤

## 1. 安装 Git（若未安装）

- 下载：https://git-scm.com/download/win
- 安装时勾选 "Add Git to PATH"
- 安装完成后**重启终端**或 Cursor

## 2. 在 GitHub 创建新仓库

1. 登录 https://github.com
2. 点击右上角 **+** → **New repository**
3. 填写仓库名（如 `humanoid-policy-viewer`）
4. 选择 **Public**
5. **不要**勾选 "Add a README"
6. 点击 **Create repository**

## 3. 在本地执行命令

打开 **CMD** 或 **PowerShell**，依次执行：

```cmd
cd c:\Users\29677\Desktop\humanoid\humanoid-policy-viewer

git init
git add .
git commit -m "Initial commit: humanoid policy viewer with bridge"

git branch -M main
git remote add origin https://github.com/CCCCris718/Humanoid.git
git push -u origin main
```

## 4. 若提示需要登录

- **HTTPS**：会提示输入 GitHub 用户名和密码（密码用 Personal Access Token，不是登录密码）
- **SSH**：需先配置 SSH 密钥，然后用 `git@github.com:用户名/仓库名.git` 作为 remote

## 5. 创建 Personal Access Token（HTTPS 推送时）

1. GitHub → Settings → Developer settings → Personal access tokens
2. Generate new token (classic)
3. 勾选 `repo` 权限
4. 生成后复制 token，在推送时用 token 替代密码
