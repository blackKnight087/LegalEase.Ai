import { useEffect, useState } from "react";
import { Outlet, useNavigate } from "react-router-dom";
import * as api from "../api/client.js";
import Sidebar from "./Sidebar.jsx";

export default function Layout() {
  const [llmOnline, setLlmOnline] = useState(false);
  const [history, setHistory] = useState([]);
  const navigate = useNavigate();

  useEffect(() => {
    api.fetchStatus().then((d) => setLlmOnline(d.llm?.online)).catch(() => {});
    api.fetchChatHistory(8).then((d) => setHistory(d.sessions || [])).catch(() => {});
  }, []);

  const onNewChat = () => {
    navigate("/");
    window.dispatchEvent(new CustomEvent("legalease:new-chat"));
  };

  const onLoadSession = (s) => {
    navigate("/", { state: { session: s } });
  };

  return (
    <div className="w-full h-screen flex overflow-hidden bg-canvas">
      <Sidebar
        history={history}
        onNewChat={onNewChat}
        onLoadSession={onLoadSession}
        llmOnline={llmOnline}
      />
      <div className="flex-1 flex flex-col h-full min-w-0 overflow-hidden">
        <Outlet />
      </div>
    </div>
  );
}
