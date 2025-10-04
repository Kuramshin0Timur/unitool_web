module.exports = {
  apps: [
    {
      name: "UNITOOL",
      script: "venv/bin/gunicorn",
      args: "-w 4 -b 0.0.0.0:80 app:app",
      interpreter: "none"
    }
  ]
};
