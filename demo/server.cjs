const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
http.createServer((req,res) => {
  res.writeHead(200, {'content-type':'text/html; charset=utf-8'});
  res.end(fs.readFileSync(path.join(__dirname,'index.html')));
}).listen(4173, '127.0.0.1', () => console.log('Synthetic StreamBox app listening on 4173'));
