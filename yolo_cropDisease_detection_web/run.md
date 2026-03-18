#鏌ョ湅ai鏄惁鍚敤
http://localhost:5000/ai/status
# 椤圭洰杩愯鎵嬪唽锛圵indows PowerShell锛?
鏈墜鍐屾寚瀵煎湪鏈湴涓€娆℃€ц窇璧峰悗绔紙Spring Boot 9999锛夈€佹繁搴﹀涔犳湇鍔★紙Flask 5000锛夊拰鍓嶇锛圴ite 8888/8889锛夛紝骞跺畬鎴愮鍒扮鑱旇皟楠岃瘉銆?
鐩綍:
- 鐜鍑嗗
- 鏁版嵁搴撳鍏?- 鍚姩 Flask锛?000锛?- 鍚姩 Spring Boot锛?999锛?- 鍚姩鍓嶇 Vite锛?888/8889锛?- 绔埌绔仈璋冮獙璇?- 甯歌闂涓庢帓閿?
---

## 鐜鍑嗗
- 鎿嶄綔绯荤粺锛歐indows锛岀粓绔細PowerShell锛堥粯璁わ級
- Node.js 鈮?16锛堜綘褰撳墠涓?v22.x锛屽彲鐢級
- Maven Wrapper 宸插唴缃紙鏃犻渶鍗曠嫭瀹夎 Maven锛?- Python Conda 鐜锛歚yolov8`锛堝凡瀛樺湪锛?- MySQL锛堢敤浜庡鍏?`cropdisease` 搴擄級

寤鸿灏?PowerShell 杈撳嚭缂栫爜璁句负 UTF-8 浠ラ伩鍏嶄腑鏂囦贡鐮侊紙鍙€夛級锛?```powershell
chcp 65001 | Out-Null
$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
```

## 鏁版嵁搴撳鍏?- MySQL 鍒涘缓鏁版嵁搴撳苟瀵煎叆 SQL锛?  1. 鍒涘缓搴擄細`cropdisease`
  2. 瀵煎叆鏂囦欢锛歚yolo_cropDisease_detection_web/cropdisease.sql`
- Spring Boot 榛樿杩炴帴锛?  - URL: `jdbc:mysql://localhost:3306/cropdisease`
  - 鐢ㄦ埛/瀵嗙爜锛歚root/123456`锛堝涓庝綘鏈湴涓嶅悓锛岃鍦?`yolo_cropDisease_detection_web/yolo_cropDisease_detection_springboot/src/main/resources/application.properties` 涓慨鏀癸級

## 鍚姩 Flask锛?000锛?鍦ㄤ粨搴撴牴鐩綍鎵ц锛?```powershell
(D:\Software\anaconda3\envs\yolo11) ; (conda activate yolo11)
cd /d D:\Software\yolo11\ultralytics-main\Web\yolo_cropDisease_detection_web\yolo_cropDisease_detection_web\yolo_cropDisease_detection_flask
python .\main.py
```
鍚姩鎴愬姛鍚庯紝绔彛 5000 浼氬浜?LISTENING銆?
## 鍚姩 Spring Boot锛?999锛?鍦ㄦ柊鐨?PowerShell 绐楀彛鎵ц锛?```powershell
cd /d D:\Software\yolo11\ultralytics-main\Web\yolo_cropDisease_detection_web\yolo_cropDisease_detection_web\yolo_cropDisease_detection_springboot
.\mvnw.cmd spring-boot:run -DskipTests
```
鍚姩鎴愬姛鍚庯紝绔彛 9999 浼氬浜?LISTENING銆?
> 濡傛灉鎻愮ず 鈥淧ort 9999 is already in use鈥濓紝璇存槑宸叉湁瀹炰緥鍦ㄨ繍琛岋紝鍙拷鐣ユ垨缁撴潫鏃ц繘绋嬪悗閲嶅惎銆?
## 鍚姩鍓嶇 Vite锛?888/鑻ュ崰鐢ㄥ垯 8889锛?鍦ㄦ柊鐨?PowerShell 绐楀彛鎵ц锛?```powershell
cd /d D:\Software\yolo11\ultralytics-main\Web\yolo_cropDisease_detection_web\yolo_cropDisease_detection_web\yolo_cropDisease_detection_vue
npm run dev
```
鎴愬姛鍚庣粓绔細鎵撳嵃锛?- Local: `http://localhost:8888/`
- 鑻?8888 琚崰鐢紝浼氳嚜鍔ㄥ垏鎹负 `http://localhost:8889/`

Vite 浠ｇ悊閰嶇疆锛?- `/api` 鈫?`http://localhost:9999/`
- `/flask` 鈫?`http://localhost:5000/`

`.env.development` 宸茶瀹氾細
```
VITE_API_DOMAIN = '/'
```
鍓嶇鐨?`axios` 浼氫互鏍硅矾寰勪綔涓?baseURL锛屼究浜庨€氳繃 Vite 浠ｇ悊杞彂銆?
## 绔埌绔仈璋冮獙璇?纭涓変釜绔彛鍧囧湪鐩戝惉锛?```powershell
netstat -ano -p TCP | findstr ":5000"
netstat -ano -p TCP | findstr ":9999"
netstat -ano -p TCP | findstr ":8888"
```
濡傛灉 8888 娌℃湁鐩戝惉锛孷ite 鍙兘鍦?8889锛?```powershell
netstat -ano -p TCP | findstr ":8889"
```

閫氳繃鍓嶇浠ｇ悊鍙戣捣娉ㄥ唽锛堝湪 PowerShell 涓敤涓€琛屽懡浠わ級锛?```powershell
$u = 'proxy' + [guid]::NewGuid().ToString('N').Substring(0,6); $payload = @{ username = $u; password = '123456' } | ConvertTo-Json -Compress; Invoke-RestMethod -Method Post -Uri 'http://localhost:8888/api/user/register' -ContentType 'application/json' -Body $payload | ConvertTo-Json -Depth 5
```
- 鑻?Vite 鍦?8889锛岃鏀逛负锛?```powershell
$u = 'proxy' + [guid]::NewGuid().ToString('N').Substring(0,6); $payload = @{ username = $u; password = '123456' } | ConvertTo-Json -Compress; Invoke-RestMethod -Method Post -Uri 'http://localhost:8889/api/user/register' -ContentType 'application/json' -Body $payload | ConvertTo-Json -Depth 5
```
杩斿洖 `{"code":"0", ...}` 琛ㄧず鎴愬姛銆?
涔熷彲浠ョ洿鎺ュ湪娴忚鍣ㄦ墦寮€鍓嶇椤甸潰 `http://localhost:8888/`锛堟垨 `8889`锛夎繘琛屽浘褰㈠寲鎿嶄綔娴嬭瘯銆?
## 甯歌闂涓庢帓閿?- Vite 鏄剧ず Sass/Node deprecation 璀﹀憡锛?  - 涓嶅奖鍝嶈繍琛屻€傚悗缁彲鑰冭檻鐢?`sass-embedded` 骞跺皢 `@import` 杩佺Щ涓?`@use/@forward`銆?- 绔彛鍗犵敤锛?  - 5000/9999/8888 濡傛灉鍐茬獊锛岃缁撴潫鏃ц繘绋嬫垨璋冩暣绔彛銆?- 涓枃鏄剧ず涔辩爜锛?  - 鍏堣繍琛岋細
    ```powershell
    chcp 65001 | Out-Null
    $OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
    ```
- 鐩存帴鎵撳悗绔祴璇曪紙缁曡繃鍓嶇浠ｇ悊锛夛細
  ```powershell
  # Spring Boot 娉ㄥ唽鐩磋繛
  Invoke-RestMethod -Method Post -Uri 'http://localhost:9999/user/register' -ContentType 'application/json' -Body '{"username":"testuser","password":"123456"}'
  # Flask 鍋ュ悍/鎺ュ彛鏍规嵁浣犵殑璺敱鑷璋冪敤
  ```

## 涓€閿惎鍔紙鍙€夛級
濡傞渶鍦?VS Code 涓竴閿悓鏃惰捣涓夌锛屾垜鍙互甯綘娣诲姞 `.vscode/tasks.json` 浠诲姟閰嶇疆锛屽疄鐜板苟琛屽惎鍔?Flask / Spring Boot / Vite銆傞渶瑕佺殑璇濆憡璇夋垜锛屾垜鐩存帴琛ヤ笂閰嶇疆銆?
