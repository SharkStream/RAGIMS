/**
 * App shell (H1 step 1 + K5 auth): ProLayout sidebar with the four MVP
 * routes: 文档 / 任务 / 检索测试 / 设置. Pages are H2–H5 deliverables.
 *
 * K5: /login is public; everything else requires a session (route guard) and
 * shows the current identity with a logout action in the header.
 */
import { ProLayout } from "@ant-design/pro-components";
import {
  CloudUploadOutlined,
  FileTextOutlined,
  LogoutOutlined,
  SearchOutlined,
  SettingOutlined,
  UnorderedListOutlined,
  UserOutlined,
} from "@ant-design/icons";
import { Dropdown } from "antd";
import { Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import type { ReactNode } from "react";
import DocumentsPage from "./pages/documents";
import JobsPage from "./pages/jobs";
import LoginPage from "./pages/login";
import SearchTestPage from "./pages/search-test";
import SettingsPage from "./pages/settings";
import { clearSession, getStoredUser, getToken, type StoredUser } from "./auth";

/** Route guard: no session → /login (preserving the deep link). */
function RequireAuth({ children }: { children: ReactNode }) {
  const location = useLocation();
  if (!getToken()) {
    const next = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`/login?next=${next}`} replace />;
  }
  return <>{children}</>;
}

export default function App() {
  const location = useLocation();
  const navigate = useNavigate();
  const user: StoredUser | null = getStoredUser();

  if (location.pathname === "/login") {
    return (
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    );
  }

  return (
    <ProLayout
      title="RAGIMS"
      logo={<FileTextOutlined />}
      layout="mix"
      location={{ pathname: location.pathname }}
      avatarProps={{
        icon: <UserOutlined />,
        style: { backgroundColor: "#1677ff" },
        render: (_props, dom) => (
          <Dropdown
            menu={{
              items: [
                {
                  key: "identity",
                  label: `${user?.username ?? "未登录"}（${user?.role ?? "-"}）`,
                  disabled: true,
                },
                { type: "divider" },
                {
                  key: "logout",
                  icon: <LogoutOutlined />,
                  label: "退出登录",
                  onClick: () => {
                    clearSession();
                    navigate("/login", { replace: true });
                  },
                },
              ],
            }}
          >
            {dom}
          </Dropdown>
        ),
        // Avatar with an identity suffix when logged in
        title: undefined,
      }}
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
        <Route
          path="/"
          element={<Navigate to="/documents" replace />}
        />
        <Route
          path="/documents"
          element={
            <RequireAuth>
              <DocumentsPage />
            </RequireAuth>
          }
        />
        <Route
          path="/jobs"
          element={
            <RequireAuth>
              <JobsPage />
            </RequireAuth>
          }
        />
        <Route
          path="/search-test"
          element={
            <RequireAuth>
              <SearchTestPage />
            </RequireAuth>
          }
        />
        <Route
          path="/settings"
          element={
            <RequireAuth>
              <SettingsPage />
            </RequireAuth>
          }
        />
        <Route path="/login" element={<LoginPage />} />
        <Route path="*" element={<Navigate to="/documents" replace />} />
      </Routes>
    </ProLayout>
  );
}
