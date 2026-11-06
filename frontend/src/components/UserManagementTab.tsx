/**
 * K7 · 用户管理（admin-only）：本租户账号列表 + 创建 + 角色/状态/密码维护。
 * 防自锁：后端拒绝 admin 修改自己，前端也不渲染对自己的操作按钮。
 */
import { useCallback, useEffect, useState } from "react";
import {
  Button,
  Card,
  Form,
  Input,
  Modal,
  Popconfirm,
  Select,
  Space,
  Table,
  Tag,
  message,
} from "antd";
import { usersApi, errorMessage, type ManagedUser } from "../api";
import { getStoredUser } from "../auth";

const ROLE_COLORS: Record<string, string> = {
  admin: "gold",
  editor: "blue",
  viewer: "default",
};

export default function UserManagementTab() {
  const me = getStoredUser();
  const [rows, setRows] = useState<ManagedUser[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [pwTarget, setPwTarget] = useState<ManagedUser | null>(null);
  const [form] = Form.useForm();
  const [pwForm] = Form.useForm();

  const load = useCallback(
    async (p: number) => {
      setLoading(true);
      try {
        const r = await usersApi.list({ page: p, page_size: 20 });
        setRows(r.items);
        setTotal(r.total);
        setPage(p);
      } catch (err) {
        message.error(errorMessage(err));
      } finally {
        setLoading(false);
      }
    },
    [],
  );

  useEffect(() => {
    void load(1);
  }, [load]);

  const onCreate = async () => {
    const v = await form.validateFields();
    try {
      await usersApi.create(v);
      message.success(`已创建 ${v.username}`);
      setCreateOpen(false);
      form.resetFields();
      void load(1);
    } catch (err) {
      message.error(errorMessage(err));
    }
  };

  const onPatch = async (
    u: ManagedUser,
    body: { role?: string; status?: string; password?: string },
  ) => {
    try {
      await usersApi.patch(u.id, body);
      message.success(`已更新 ${u.username}`);
      void load(page);
    } catch (err) {
      message.error(errorMessage(err));
    }
  };

  const onResetPassword = async () => {
    if (!pwTarget) return;
    const v = await pwForm.validateFields();
    await onPatch(pwTarget, { password: v.password });
    setPwTarget(null);
    pwForm.resetFields();
  };

  return (
    <Card
      title="用户管理（本租户）"
      extra={
        <Button type="primary" onClick={() => setCreateOpen(true)}>
          新建用户
        </Button>
      }
    >
      <Table<ManagedUser>
        rowKey="id"
        size="small"
        loading={loading}
        dataSource={rows}
        pagination={{ current: page, total, pageSize: 20, onChange: (p) => void load(p) }}
        columns={[
          { title: "用户名", dataIndex: "username" },
          {
            title: "角色",
            dataIndex: "role",
            width: 110,
            render: (role: string) => <Tag color={ROLE_COLORS[role]}>{role}</Tag>,
          },
          {
            title: "状态",
            dataIndex: "status",
            width: 100,
            render: (s: string) =>
              s === "active" ? <Tag color="green">active</Tag> : <Tag color="red">disabled</Tag>,
          },
          { title: "创建时间", dataIndex: "created_at", width: 170, render: (t: string) => t?.slice(0, 19).replace("T", " ") },
          {
            title: "操作",
            width: 240,
            render: (_, u) =>
              u.id === me?.id ? (
                <span style={{ color: "#999" }}>当前账号</span>
              ) : (
                <Space size="small">
                  <Select
                    size="small"
                    value={u.role}
                    style={{ width: 92 }}
                    onChange={(role) => void onPatch(u, { role })}
                    options={["admin", "editor", "viewer"].map((r) => ({ value: r, label: r }))}
                  />
                  {u.status === "active" ? (
                    <Popconfirm
                      title="禁用后该用户立即无法登录"
                      onConfirm={() => void onPatch(u, { status: "disabled" })}
                    >
                      <Button size="small" danger>
                        禁用
                      </Button>
                    </Popconfirm>
                  ) : (
                    <Button size="small" onClick={() => void onPatch(u, { status: "active" })}>
                      启用
                    </Button>
                  )}
                  <Button
                    size="small"
                    onClick={() => {
                      setPwTarget(u);
                      pwForm.resetFields();
                    }}
                  >
                    重置密码
                  </Button>
                </Space>
              ),
          },
        ]}
      />

      <Modal
        title="新建用户"
        open={createOpen}
        onOk={() => void onCreate()}
        onCancel={() => setCreateOpen(false)}
        destroyOnClose
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="username"
            label="用户名"
            rules={[
              { required: true },
              { pattern: /^[A-Za-z0-9_.-]{2,64}$/, message: "2-64 位字母/数字/._-" },
            ]}
          >
            <Input placeholder="alice" />
          </Form.Item>
          <Form.Item
            name="password"
            label="初始密码"
            rules={[
              { required: true },
              {
                pattern: /^(?=.*[A-Za-z])(?=.*\d).{8,128}$/,
                message: "≥8 位且含字母和数字",
              },
            ]}
          >
            <Input.Password />
          </Form.Item>
          <Form.Item name="role" label="角色" initialValue="viewer" rules={[{ required: true }]}>
            <Select
              options={[
                { value: "admin", label: "admin（全权）" },
                { value: "editor", label: "editor（读写文档）" },
                { value: "viewer", label: "viewer（只读）" },
              ]}
            />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={pwTarget ? `重置密码：${pwTarget.username}` : ""}
        open={pwTarget !== null}
        onOk={() => void onResetPassword()}
        onCancel={() => setPwTarget(null)}
        destroyOnClose
      >
        <Form form={pwForm} layout="vertical">
          <Form.Item
            name="password"
            label="新密码"
            rules={[
              { required: true },
              {
                pattern: /^(?=.*[A-Za-z])(?=.*\d).{8,128}$/,
                message: "≥8 位且含字母和数字",
              },
            ]}
          >
            <Input.Password />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  );
}
