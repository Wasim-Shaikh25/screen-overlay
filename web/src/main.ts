import { startApp } from "./app.ts";
import "./styles.css";

const mount = document.getElementById("mount");
const parked = document.getElementById("parked");
if (!mount || !parked) {
  throw new Error("AI Overlay is missing its page shell.");
}
startApp(mount, parked);
