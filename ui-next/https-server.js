/* eslint-disable @typescript-eslint/no-require-imports */
const https = require('https');
const fs = require('fs');
const path = require('path');
const { parse } = require('url');

// The standalone server.js exported from Next.js build
// We need to require it. It usually exports a handler or starts a server.
// In Next.js standalone, server.js starts its own http server.
// To use HTTPS, we can either wrap the handler or use a proxy.

const certPath = process.env.SSL_CERTFILE || '/certs/frontend.crt';
const keyPath = process.env.SSL_KEYFILE || '/certs/frontend.key';
const caPath = process.env.NODE_EXTRA_CA_CERTS || '/certs/ca.crt';

if (!fs.existsSync(certPath) || !fs.existsSync(keyPath)) {
  console.error('SSL certificates not found. Falling back to HTTP.');
  require('./server.js');
} else {
  const options = {
    key: fs.readFileSync(keyPath),
    cert: fs.readFileSync(certPath),
  };

  if (fs.existsSync(caPath)) {
    options.ca = fs.readFileSync(caPath);
  }

  // Load the next handler
  // Next.js standalone server.js starts its own server on port 3000 by default.
  // We want it to listen on HTTPS instead.
  
  process.env.NODE_ENV = 'production';
  process.env.PORT = '3001'; // Let the original server run on a different internal port
  
  // Start the original server in the background
  require('./server.js');

  // Create an HTTPS proxy to the internal Next.js server
  const httpProxy = require('http');

  https.createServer(options, (req, res) => {
    const proxyReq = httpProxy.request({
      host: 'localhost',
      port: 3001,
      path: req.url,
      method: req.method,
      headers: req.headers
    }, (proxyRes) => {
      res.writeHead(proxyRes.statusCode, proxyRes.headers);
      proxyRes.pipe(res, { end: true });
    });

    req.pipe(proxyReq, { end: true });
    
    proxyReq.on('error', (e) => {
      console.error(`Proxy error: ${e.message}`);
      res.statusCode = 502;
      res.end('Bad Gateway');
    });
  }).listen(3000, () => {
    console.log('HTTPS Proxy Server running on port 3000');
  });
}
