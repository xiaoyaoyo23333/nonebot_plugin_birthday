# nonebot_plugin_birthday
一个偏个人用的群聊生日推送插件<br>

在生日当天0时0分准时推送生日通知<br>
生日当天录入的日期立即发送推送通知<br>
会检查是否录入不存在的日期<br>
使用东八区时间<br>
发送成功/失败同步输出到日志以及对应群聊<br>
各群聊各自配置<br>




## 安装方法：<br>
请使用nb-cli脚手架新建一个插件文件夹<br>
将__init__.py的代码复制进去<br>

## 使用方法：<br>
各群聊成员可使用<br>
“添加生日 qq号 月 日”/“添加生日 @目标群友 月 日”录入生日，（如：添加生日 1111111 12 31）<br>
“修改生日 QQ号 月 日”/“修改生日 @目标群友 月 日”可顶掉原先录入的生日日期<br>
“删除生日 qq号”/“删除生日 @目标群友”删除生日，<br>
“生日列表”查看该群聊已录入的生日，<br>
数据存储：/data/bitrhday/各群聊单独的.json文件

## 使用示例：<br>
### 生日当天添加生日，bot即时推送生日通知：
![111](https://github.com/xiaoyaoyo23333/nonebot_plugin_birthday/blob/main/3A17FCD5B904F4F25EA2CCFD3C0EBC41.jpg)<br>
<br>
### 添加定期生日，生日当天0时0分bot准时推送生日通知：
![222](https://github.com/xiaoyaoyo23333/nonebot_plugin_birthday/blob/main/0325114BAA7DE5453F9D6AFD83F38EB5.png)<br>
![333](https://github.com/xiaoyaoyo23333/nonebot_plugin_birthday/blob/main/1E9375C2E02D9C2475539DA7DBFA4380.png)<br>
