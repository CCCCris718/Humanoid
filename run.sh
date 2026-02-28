# 终端1 — bridge（自动管理 SSH 隧道）
cd /Users/physhjt/Documents/GitHub/humanoid-policy-viewer
conda activate gentle
python bridge.py

# 终端2 — web viewer
cd /Users/physhjt/Documents/GitHub/humanoid-policy-viewer
npm run dev
