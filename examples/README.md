# 虚构演示批次

`images` 里的 12 张 PNG 是用程序绘制的测试图形，不含实际研究图片、真实证件或个人信息。两份 CSV 的筛选人是虚构的 `Demo A`、`Demo B`。

## 操作

1. 打开上一层目录中的 `筛选工具.html`。
2. 点“选择／切换文件夹”，只选择本目录里的 `images`。
3. 切到“双人比对”，打开“导入／管理 CSV”。
4. 先选 `reviewer-a.csv`，可以关掉弹窗后再回来选择 `reviewer-b.csv`；也可同时选择两份。
5. 检查通过后开始比对。

初始状态应为：全部 12、有分歧 4、一致保留 2、一致排除 2、待补筛 4。

| 图片 | Demo A | Demo B | 状态 |
| --- | --- | --- | --- |
| sample_001.png | Yes | Yes | 一致保留 |
| sample_002.png | No | No | 一致排除 |
| sample_003.png | Yes | No | 有分歧 |
| sample_004.png | No | Yes | 有分歧 |
| sample_005.png | Yes | Yes | 一致保留 |
| sample_006.png | No | No | 一致排除 |
| sample_007.png | Yes | No | 有分歧 |
| sample_008.png | No | Yes | 有分歧 |
| sample_009.png | Yes | 未筛选 | 待补筛 |
| sample_010.png | 未筛选 | No | 待补筛 |
| sample_011.png | 未筛选 | 未筛选 | 待补筛 |
| sample_012.png | 未筛选 | 未筛选 | 待补筛 |

在“有分歧”中试用 `1／2` 和撤销，再导出完整汇总 CSV。对示例的操作也会保存在当前浏览器中；如需恢复初始状态，重新导入这两份原始示例 CSV 并开始比对。
