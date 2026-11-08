# TVBox 多仓自动更新模板

这个模板保留多个独立单仓，不合并不同仓库的 Spider/JAR，并生成适合 FongMi 及支持多仓的 TVBox 分支使用的 `urls` 订阅。

## 第一次使用

第一步：把本目录全部内容上传到名为 `tvbox-config` 的公开 GitHub 仓库，默认分支保持 `main`。

第二步：确认 `.github/workflows/update.yml` 已上传，没有漏掉隐藏的 `.github` 目录。

第三步：在 `Settings → Actions → General` 中启用 `Read and write permissions`。

第四步：在 `Settings → Pages` 中把 Source 设为 `GitHub Actions`。

第五步：在 Actions 中手动运行 `Update TVBox subscriptions and publish Pages`。

第六步：部署成功后，使用下面的固定地址，替换为你的 GitHub 用户名：

```text
https://你的GitHub用户名.github.io/tvbox-config/subscription.json
```

## 输出文件

`output/subscription.json`：默认推荐仓，适合日常使用。

`output/qist-all.json`：Qist 项目当前可用的八个通用仓，不含成人专用配置，也不含 JAR MD5 校验不一致的 0821/0826。

`output/subscription-full.json`：全部成功或缓存的仓，包含高级和 HTTP 备选。

`output/status.json`：每个来源的抓取时间、状态和错误信息。

## 添加或停用来源

编辑 `config/sources.json`。每个来源需要唯一的英文 `id`、显示名称 `name` 和至少一个 `urls` 地址。

`recommended: true` 控制来源进入默认推荐订阅；`false` 只保留在完整订阅中。

脚本只接受含非空 `sites` 的单仓。不要把另一个多仓索引直接作为单仓来源嵌套进去。

## 自动更新与缓存

工作流计划在北京时间每天 10:00 和 22:00 运行，也可能因 GitHub 排队而延迟。

上游失败时，脚本会沿用上次成功缓存，并在名称后标记“缓存”。缓存只保证配置文件暂时可读取，不代表内部站点仍然有效。

缓存配置中的 `./` 和 `../` 依赖会改为原始绝对地址，避免 JAR、JS、Python 或直播文件错误地指向你的新仓库。

## 重要限制

普通 TVBox 如果没有“多仓/订阅”入口，请直接使用某个单仓地址，不要填本模板生成的多仓文件。

自动更新不能保证第三方播放源永久有效，也不会让 FongMi 在多个仓库之间自动故障转移。仓库切换仍需手动完成。

不要在公共仓库存放 Token、Cookie、WebDAV 密码或私人代理地址。只播放自己拥有、已获授权或合法公开的内容。
