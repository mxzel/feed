# feed

集中维护订阅转换器，将没有可用 RSS 的公开内容转换为标准订阅源。

每个来源使用独立转换器。GitHub Actions 定时抓取和生成 RSS，再通过 GitHub Pages 发布固定订阅地址。

## 公开内容边界

**本仓库 `mxzel/feed` 是公开仓库。代码、提交历史、状态文件、Actions 日志和 Pages 文件均按公开内容处理。**

仅存放公开来源的转换代码和必要的公开元数据。禁止上传密钥、令牌、Cookie、账户导出、私人订阅、阅读记录、个人画像、私人笔记和内部资料。不得从其他项目整目录复制配置、数据或运行日志。

## 订阅地址

- [HackerTube RSS](https://mxzel.github.io/feed/hackertube.xml)
- [订阅源首页](https://mxzel.github.io/feed/)

HackerTube 转换器保留视频简介、HN 推荐理由、频道、时长、难度和主题。
简介和推荐理由来自站方整理，不是视频全文或字幕。
首页推荐包含旧视频；RSS 日期采用首次发现时间，原始发布时间列在正文中。
视频 ID 用于去重。状态文件保留所有已发现视频，RSS 提供最近发现的 200 条。

## 自动更新与发布

工作流 `.github/workflows/publish.yml` 每天 UTC 00:17（北京时间 08:17）运行。
修改转换脚本或工作流也会触发运行，可在 Actions 页面手动执行「更新订阅并发布」。

1. 运行离线测试。
2. 从公开 API 生成 RSS。
3. 将公开视频状态提交到 `data/hackertube.json`。
4. 仅上传 `public/`，再发布到 GitHub Pages。

API 请求失败或格式校验失败时，本轮不会发布，线上保留上次成功的版本。
GitHub 定时任务允许延迟；公开仓库连续 60 天无活动时，GitHub 会停用定时任务。
默认工作流令牌保持只读；保存状态和发布任务分别声明所需权限。

## 本地运行

仅需 Python 3.10+ 标准库，无第三方依赖。

```sh
python3 -m unittest discover -s tests -v
python3 scripts/hackertube.py \
  --api-url https://hackertube.org/api/feed \
  --feed-url https://mxzel.github.io/feed/hackertube.xml \
  --state data/hackertube.json \
  --output-dir public
```

`public/` 是生成目录，不提交到代码仓库。新增转换器时，复用工作流并只把发布文件写入此目录。
