#!/bin/bash
BASE="http://127.0.0.1:5000"
JAR=/tmp/e2e_jar.txt
rm -f "$JAR"

echo "== 1. 登录 demo =="
curl -s -c "$JAR" "$BASE/auth/login" -o /tmp/l.html
T=$(grep -o 'name="csrf_token"[^>]*' /tmp/l.html | grep -o 'value="[^"]*"' | head -1 | cut -d'"' -f2)
curl -s -b "$JAR" -c "$JAR" -L --data-urlencode "csrf_token=$T" \
  --data-urlencode "email=demo@ekkosys.cn" --data-urlencode "password=demo123" \
  --data-urlencode "remember=y" -o /dev/null -w "%{url_effective}\n" "$BASE/auth/login"

echo "== 2. 上传 md =="
curl -s -b "$JAR" -c "$JAR" "$BASE/prep/content" -o /tmp/c.html
T2=$(grep -o 'name="csrf_token"[^>]*' /tmp/c.html | grep -o 'value="[^"]*"' | head -1 | cut -d'"' -f2)
# 用 -D 抓响应头拿 Location
curl -s -b "$JAR" -c "$JAR" -D /tmp/h.txt --data-urlencode "csrf_token=$T2" \
  --data-urlencode "text=# 分析
- **分析：** 这是加粗的重点
- \`while(t--)\` 是代码
- **输入样例：** \`2023\`
- **输出样例：** \`7\`
- 普通文本" \
  -o /dev/null "$BASE/prep/content"
LOC=$(grep -i '^location:' /tmp/h.txt | tr -d '\r\n' | awk '{print $2}')
JOB_ID=$(echo "$LOC" | grep -oE '[a-f0-9-]{36}')
echo "job_id: $JOB_ID"
echo "location: $LOC"

echo "== 3. 选风格 =="
curl -s -b "$JAR" -c "$JAR" "$BASE$LOC" -o /tmp/s.html
T3=$(grep -o 'name="csrf_token"[^>]*' /tmp/s.html | grep -o 'value="[^"]*"' | head -1 | cut -d'"' -f2)
curl -s -b "$JAR" -c "$JAR" -X POST -L --data-urlencode "csrf_token=$T3" \
  --data-urlencode "style=devblue" --data-urlencode "title=格式测试" \
  -o /dev/null -w "%{url_effective}\n" "$BASE/prep/content/$JOB_ID/style"
echo "等待生成..."
sleep 8

echo "== 4. 下载 =="
curl -s -b "$JAR" -c "$JAR" "$BASE/prep/result/$JOB_ID" -o /tmp/result.html
DL=$(grep -oE '/prep/download/[^\"]+' /tmp/result.html | head -1)
echo "download: $DL"
curl -s -b "$JAR" -c "$JAR" "$BASE$DL" -o /tmp/course.html

echo "== 5. 验证 =="
echo "-- strong:"; grep -c '<strong>' /tmp/course.html
echo "-- code:"; grep -c '<code>' /tmp/course.html
echo "-- ** 残留:"; grep -c '\*\*' /tmp/course.html
echo "-- \` 残留:"; grep -c '\`' /tmp/course.html
echo "-- bullets:"
grep -oE '<li>[^<]{0,80}' /tmp/course.html | head -8
