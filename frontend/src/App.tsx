/**
 * App shell (H1 step 1): ProLayout sidebar with the four MVP routes:
 * 文档 / 任务 / 检索测试 / 设置. Pages are H2–H5 deliverables.
 */
import { ProLayout } from "@ant-design/pro-components";
import {
  CloudUploadOutlined,
  FileTextOutlined,
  SearchOutlined,
  SettingOutlined,
  UnorderedListOutlined,
} from "@ant-design/icons";
import { Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import DocumentsPage from "./pages/documents";
import JobsPage from "./pages/jobs";
import SearchTestPage from "./pages/search-test";
import SettingsPage from "./pages/settings";

export default function App() {
  const location = useLocation();
  const navigate = useNavigate();
  return (
    <ProLayout
      title="RAGIMS"
      logo={<FileTextOutlined />}
      layout="mix"
      location={{ pathname: location.pathname }}
      menu={{
        request: async () => [
          { path: "/documents", name: "文档", icon: <CloudUploadOutlined /> },
          { path: "/jobs", name: "任务", icon: <UnorderedListOutlined /> },
          { path: "/search-test", name: "检索测试", icon: <SearchOutlined /> },
          { path: "/settings", name: "设置", icon: <SettingOutlined /> },
        ],
      }}
      menuItemRender={(item, dom) => (
        <a
          onClick={() => {
            if (item.path) navigate(item.path);
          }}
        >
          {dom}
        </a>
      )}
    >
      <Routes>
        <Route path="/" element={<Navigate to="/documents" replace />} />
        <Route path="/documents" element={<DocumentsPage />} />
        <Route path="/jobs" element={<JobsPage />} />
        <Route path="/search-test" element={<SearchTestPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="*" element={<Navigate to="/documents" replace />} />
      </Routes>
    </ProLayout>
  );
}
