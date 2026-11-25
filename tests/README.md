# 框选回归测试

`marquee.cjs` 用真实鼠标和键盘操作浏览器，覆盖框选、边缘滚动、批量 Yes／No、整批撤销、跨页、待补筛拦截、双人原始记录保护、刷新恢复、汇总导出，以及直接打开 HTML 的模式。

需要 Node.js、Playwright、Python 和可用的 Chromium 浏览器。测试会自行生成 2005 张虚构图片，创建独立浏览器上下文，启动本机临时服务，并把结果写入新建的临时目录；不会读取日常图片目录或浏览器个人资料。控制台最后的 `ARTIFACTS` 行是检查记录与截图所在目录。

在仓库根目录运行：

```text
node tests/marquee.cjs
```

可通过环境变量指定本机环境：

| 变量 | 用途 |
| --- | --- |
| `IMAGE_REVIEW_PYTHON` | Python 可执行文件；默认 `python` |
| `IMAGE_REVIEW_BROWSER` | Edge／Chrome 等 Chromium 浏览器路径；留空时用 Playwright 的浏览器 |
| `PLAYWRIGHT_MODULE` | Playwright 模块路径；默认从已安装的 `playwright` 包加载 |
| `IMAGE_REVIEW_TEST_PORT` | 临时服务端口；默认 8891，应使用未占用端口 |
| `IMAGE_REVIEW_TEST_OUTPUT` | 检查记录的父目录；默认系统临时目录，每次创建独立子目录 |

检查记录不包含真实研究图片或真实标注，不需要上传到仓库。
