# 上传到 GitHub

这份文件夹已经按仓库结构整理。上传时进入文件夹，把其中的文件和子文件夹放到仓库根目录，让 `README.md`、`筛选工具.html` 直接出现在仓库首页。

## 第一次上传：网页即可完成

1. 登录 GitHub，打开 [新建仓库](https://github.com/new)。
2. 仓库名建议用 `image-review-tool`。描述可填：`Local image screening with CSV-based dual-review comparison and adjudication.`
3. 选择可见性。建议先建 Private（私有）仓库，自己检查后再决定是否公开；Public（公开）仓库所有人都能看到并下载。
4. 不勾选额外生成 README、`.gitignore`，这些文件已经准备好。许可证可以暂时不选，待代码权利人决定后再补。
5. 点击“Create repository”。
6. 空仓库首页点击“uploading an existing file”；已有文件的仓库用“Add file → Upload files”。
7. 打开本发布包文件夹，把内部所有文件和子文件夹拖进上传区。不要再套一层“发布包”目录，也不要只上传压缩包。
8. 在提交说明填写：`Add image screening and CSV comparison tool`。
9. 提交到新仓库的默认分支。界面如要求先建立分支和 Pull Request，按提示提交并合并。
10. 回到仓库首页，确认 README 已正常显示，`筛选工具.html`、`examples`、`docs` 都在根目录，README 内的截图能打开。

本发布包少于 100 个文件，单个文件小于 25 MiB，适合一次网页上传。网页端支持上传文件和文件夹；如果当前浏览器无法拖入目录，可以分别进入对应目录上传。

## 给别人使用

分享仓库链接即可。下载者在仓库首页点击“Code → Download ZIP”，解压后双击 `筛选工具.html`，再选择自己的图片目录。

如果仓库为 Private，接收者需要有仓库访问权限。想直接发给同学试用，也可以发送本发布包的 ZIP，解压后同样使用。

## 发布一个版本包

源文件上传完成后，可以再创建 Release，方便别人找到可下载的版本：

1. 仓库页面进入“Releases”，选择“Draft a new release”。
2. 创建标签，例如 `v1.0.0`，表示你准备发布的第一个对外版本。
3. 标题可用“图片筛选工具：个人筛选与双人 CSV 比对”。
4. 版本说明写清已提供的功能；可以参考 `CHANGELOG.md`。
5. 把桌面上的发布包 ZIP 作为附件添加进去。
6. 检查后发布，或先保存草稿。

CSV 内部“格式版本 3”和 GitHub 的发布标签是两件事，不需要相同。

## 后续更新

第一次可以直接网页上传。后续频繁更新时，适合使用 GitHub Desktop：克隆仓库到本地，把改好的文件放回仓库，查看改动后提交并推送。工具自己不会把标注上传到 GitHub。

需要发布新版本时，更新 `CHANGELOG.md` 和截图，生成新的版本包，再新建一个 Release。

## 公开和许可证

把仓库设为 Public 是公开代码；允许他人如何复用、修改、分发，还需要明确许可证。本包没有代替你选择许可证，先整理私有仓库即可。

实际研究图像、真实筛选结果、浏览器会话备份应继续放在工作目录。此发布目录附带的图片和 CSV 均为虚构示例。

## 官方说明

- [创建仓库](https://docs.github.com/en/repositories/creating-and-managing-repositories/creating-a-new-repository)
- [上传文件](https://docs.github.com/en/repositories/working-with-files/managing-files/adding-a-file-to-a-repository)
- [从仓库下载源码](https://docs.github.com/en/repositories/working-with-files/using-files/downloading-source-code-archives)
- [创建和管理 Release](https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository)
- [为仓库选择许可证](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository)
