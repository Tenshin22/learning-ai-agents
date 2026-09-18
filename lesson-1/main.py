import urllib.request

url = 'https://httpbin.org'
with urllib.request.urlopen(url) as response:
  html_content = response.read().decode('utf-8')
  print(html_content)
