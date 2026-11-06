/**
 * K5 · 登录页：username/password → POST /auth/login → 存会话 → 回跳。
 * 登录失败显示后端统一文案（ERR_UNAUTHORIZED → 「用户名或密码错误」语义由
 * 后端 message 承载）。
 */
import { Button, Card, Form, Input, Typography } from "antd";
import { UserOutlined, LockOutlined } from "@ant-design/icons";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useState } from "react";
import { authApi, errorMessage } from "../api";
import { setSession, type StoredUser } from "../auth";

export default function LoginPage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onFinish = async (values: { username: string; password: string }) => {
    setLoading(true);
    setError(null);
    try {
      const result = await authApi.login(values.username, values.password);
      setSession(
        result.token,
        result.user as unknown as StoredUser,
      );
      const next = params.get("next") ?? "/documents";
      navigate(next, { replace: true });
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "#f0f2f5",
      }}
    >
      <Card style={{ width: 360 }}>
        <Typography.Title level={4} style={{ textAlign: "center" }}>
          RAGIMS 登录
        </Typography.Title>
        <Form onFinish={(v) => void onFinish(v as { username: string; password: string })}>
          <Form.Item
            name="username"
            rules={[{ required: true, message: "请输入用户名" }]}
          >
            <Input prefix={<UserOutlined />} placeholder="用户名" autoFocus />
          </Form.Item>
          <Form.Item
            name="password"
            rules={[{ required: true, message: "请输入密码" }]}
          >
            <Input.Password prefix={<LockOutlined />} placeholder="密码" />
          </Form.Item>
          {error && (
            <Typography.Text type="danger" style={{ display: "block", marginBottom: 12 }}>
              {error}
            </Typography.Text>
          )}
          <Button type="primary" htmlType="submit" block loading={loading}>
            登录
          </Button>
        </Form>
      </Card>
    </div>
  );
}
