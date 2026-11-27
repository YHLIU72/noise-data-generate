# 推送到 `YHLIU72/noise-data-generate`

本地实现已在空仓库状态下构建。远程仓库当前为公共仓库，默认分支名为 `main`，但在本次开发环境中命令行 Git 访问曾被网络策略阻断；因此应使用已授权的 GitHub 连接，或在本地网络恢复后按以下流程操作。

## 推荐分支流程

```powershell
git clone https://github.com/YHLIU72/noise-data-generate.git
cd noise-data-generate
git checkout -b feat/parameterized-hvac-aeroacoustic-rom

# 将本包中的 src、tests、pyproject.toml、README.md 复制到仓库根目录
python -m unittest discover -s tests -v
git add src tests pyproject.toml README.md
git commit -m "Implement parameterized HVAC aeroacoustic ROM"
git push -u origin feat/parameterized-hvac-aeroacoustic-rom
```

然后创建一个目标为 `main` 的 Pull Request。PR 描述应明确：

- 这是低阶参数化数值模拟，不是实验数据；
- 默认压力系数尚未针对实测数据标定；
- 平面波传播只在 `provenance.json` 记录的有效频率范围内具有模型内一致性；
- 测试通过并不等于实验验证完成。

## 若仓库仍显示 404

请在 GitHub 连接设置中授予 `YHLIU72/noise-data-generate` 的读取和写入权限，或使用能访问该仓库的 GitHub 账号完成一次授权。不要把个人访问令牌写入仓库、README、命令历史或聊天内容。
