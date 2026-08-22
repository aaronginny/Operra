const express = require("express");
const cors = require("cors");
const { init } = require("./db");

const app = express();

app.use(cors({ origin: "*", credentials: true }));
app.use(express.json());

// Ensure DB tables exist on every cold start (Turso is remote so init is fast)
let _ready = null;
app.use((req, res, next) => {
  if (!_ready) _ready = init();
  _ready.then(next).catch(next);
});

app.use("/api/auth",        require("./routes/auth"));
app.use("/api/buyers",      require("./routes/buyers"));
app.use("/api/sellers",     require("./routes/sellers"));
app.use("/api/matches",     require("./routes/matches"));
app.use("/api/notes",       require("./routes/notes"));
app.use("/api/commissions", require("./routes/commissions"));
app.use("/api/contacts",    require("./routes/contacts"));

// Local dev only
if (require.main === module) {
  const PORT = process.env.PORT || 3001;
  _ready = init();
  _ready.then(() => app.listen(PORT, () => console.log(`DealKnot server → http://localhost:${PORT}`)));
}

module.exports = app;
