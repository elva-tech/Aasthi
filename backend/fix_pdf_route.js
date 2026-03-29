import fs from 'fs';
import path from 'path';

const file = '/home/ravella/landed/backend/server.js';
let content = fs.readFileSync(file, 'utf8');

// Replace standard express.static with headers forcing attachment
content = content.replace(
  "app.use('/reports', express.static(path.join(__dirname, 'reports')));",
  "app.use('/reports', express.static(path.join(__dirname, 'reports'), {\n" +
  "  setHeaders: function (res, path, stat) {\n" +
  "    res.set('Content-Disposition', 'attachment');\n" +
  "    res.set('Content-Type', 'application/pdf');\n" +
  "  }\n" +
  "}));"
);

fs.writeFileSync(file, content);
console.log("Updated server.js");
