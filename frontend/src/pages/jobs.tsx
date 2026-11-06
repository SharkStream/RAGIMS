/**
 * H3 · 任务看板：列表（状态/耗时/筛选）+ 步骤时间线详情 + 重试/取消
 * + 轮询刷新（有活跃任务时每 5s 拉一次，MVP 不做 WebSocket）。
 */
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Button,
  Card,
  Descriptions,
  Drawer,
  Input,
  message,
  Popconfirm,
  Select,
  Space,
  Spin,
  Steps,
  Switch,
  Table,
  Tag,
  Typography,
} from "antd";
import type { ColumnsType, TablePaginationConfig } from "antd/es/table";
import { jobsApi, errorMessage, type JobOut, type JobStepOut } from "../api";
import { canWrite, getStoredUser } from "../auth";

const POLL_MS = 5000;

function jobStatusTag(status: string) {
  const map: Record<string, { color: string; text: string }> = {
    pending: { color: "default", text: "排队中" },
    running: { color: "processing", text: "运行中" },
    succeeded: { color: "success", text: "成功" },
    failed: { color: "error", text: "失败" },
    cancelled: { color: "warning", text: "已取消" },
  };
  const conf = map[status] ?? { color: "default", text: status };
  return <Tag color={conf.color}>{conf.text}</Tag>;
}

function stepStatus(status: string): "wait" | "process" | "finish" | "error" {
  if (status === "succeeded") return "finish";
  if (status === "failed") return "error";
  if (status === "running") return "process";
  return "wait";
}

function duration(started: string | null, finished: string | null): string {
  if (!started || !finished) return "—";
  const ms = new Date(finished).getTime() - new Date(started).getTime();
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;
}

export default function JobsPage() {
  // K5: viewer (read-only role) sees no retry/cancel controls.
  const writable = canWrite(getStoredUser());

  // ---- list ----
  const [rows, setRows] = useState<JobOut[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [status, setStatus] = useState<string | undefined>();
  const [jobType, setJobType] = useState<string | undefined>();
  const [docIdFilter, setDocIdFilter] = useState("");
  const [loading, setLoading] = useState(false);
  const [polling, setPolling] = useState(true);

  // ---- detail drawer ----
  const [detail, setDetail] = useState<JobOut | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [steps, setSteps] = useState<JobStepOut[]>([]);
  const [stepsLoading, setStepsLoading] = useState(false);
  const detailJobId = useRef<string | null>(null);

  const fetchList = useCallback(async () => {
    setLoading(true);
    try {
      const result = await jobsApi.list({
        page,
        page_size: pageSize,
        status,
        job_type: jobType,
        doc_id: docIdFilter || undefined,
      });
      setRows(result.items);
      setTotal(result.total);
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, status, jobType, docIdFilter]);

  const fetchSteps = useCallback(async (jobId: string) => {
    setStepsLoading(true);
    try {
      const result = await jobsApi.steps(jobId);
      setSteps(result.items);
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setStepsLoading(false);
    }
  }, []);

  const openDetail = useCallback(
    async (job: JobOut) => {
      try {
        const d = await jobsApi.detail(job.id);
        setDetail(d);
        detailJobId.current = job.id;
        setDetailOpen(true);
        void fetchSteps(job.id);
      } catch (err) {
        message.error(errorMessage(err));
      }
    },
    [fetchSteps],
  );

  // initial + filter-driven fetch
  useEffect(() => {
    void fetchList();
  }, [fetchList]);

  // polling (acceptance 3): refresh the list, and the open drawer's steps
  useEffect(() => {
    if (!polling) return;
    const timer = setInterval(() => {
      void fetchList();
      if (detailJobId.current && detailOpen) void fetchSteps(detailJobId.current);
    }, POLL_MS);
    return () => clearInterval(timer);
  }, [polling, fetchList, fetchSteps, detailOpen]);

  const doRetry = async (job: JobOut) => {
    try {
      const result = await jobsApi.retry(job.id);
      message.success(`已重投为新任务（job=${result.job_id.slice(0, 8)}…）`);
      void fetchList();
    } catch (err) {
      message.error(errorMessage(err));
    }
  };

  const doCancel = async (job: JobOut) => {
    try {
      const result = await jobsApi.cancel(job.id);
      message.success(`任务已标记 ${result.status}`);
      void fetchList();
      if (detailJobId.current === job.id) void fetchSteps(job.id);
    } catch (err) {
      message.error(errorMessage(err));
    }
  };

  const columns: ColumnsType<JobOut> = [
    {
      title: "任务 ID",
      dataIndex: "id",
      width: 130,
      render: (v: string) => <Typography.Text copyable={{ text: v }}>{v.slice(0, 13)}…</Typography.Text>,
    },
    { title: "类型", dataIndex: "job_type", width: 100, render: (t: string) => <Tag>{t}</Tag> },
    { title: "状态", dataIndex: "status", width: 100, render: jobStatusTag },
    { title: "耗时", key: "duration", width: 100,
      render: (_, j) => duration(j.started_at, j.finished_at) },
    { title: "创建时间", dataIndex: "created_at", width: 170,
      render: (v: string) => new Date(v).toLocaleString("zh-CN") },
    {
      title: "错误",
      dataIndex: "error_message",
      ellipsis: true,
      render: (v: string | null) => (v ? <Typography.Text type="danger">{v}</Typography.Text> : "—"),
    },
    {
      title: "操作",
      key: "actions",
      width: 220,
      render: (_, job) => (
        <Space>
          <Button size="small" onClick={() => void openDetail(job)}>详情</Button>
          {writable && job.status === "failed" && (
            <Popconfirm title="确认重投该失败任务？" onConfirm={() => void doRetry(job)}>
              <Button size="small">重试</Button>
            </Popconfirm>
          )}
          {writable && (job.status === "pending" || job.status === "running") && (
            <Popconfirm title="确认取消该任务？" onConfirm={() => void doCancel(job)}>
              <Button size="small" danger>取消</Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ];

  const pagination: TablePaginationConfig = {
    current: page,
    pageSize,
    total,
    showSizeChanger: true,
    showTotal: (t) => `共 ${t} 条`,
    onChange: (p, ps) => {
      setPage(p);
      setPageSize(ps);
    },
  };

  return (
    <Card
      title="任务看板"
      extra={
        <Space wrap>
          <Space.Compact>
            <Input
              placeholder="按 doc_id 过滤"
              style={{ width: 260 }}
              value={docIdFilter}
              onChange={(e) => {
                setDocIdFilter(e.target.value);
                setPage(1);
              }}
            />
          </Space.Compact>
          <Select
            allowClear
            placeholder="状态"
            style={{ width: 130 }}
            value={status}
            options={[
              { value: "pending", label: "排队中" },
              { value: "running", label: "运行中" },
              { value: "succeeded", label: "成功" },
              { value: "failed", label: "失败" },
              { value: "cancelled", label: "已取消" },
            ]}
            onChange={(v) => {
              setStatus(v);
              setPage(1);
            }}
          />
          <Select
            allowClear
            placeholder="类型"
            style={{ width: 130 }}
            value={jobType}
            options={[
              { value: "full", label: "full" },
              { value: "reprocess", label: "reprocess" },
            ]}
            onChange={(v) => {
              setJobType(v);
              setPage(1);
            }}
          />
          <Space.Compact>
            <Typography.Text type="secondary" style={{ marginRight: 6 }}>
              轮询 5s
            </Typography.Text>
            <Switch size="small" checked={polling} onChange={setPolling} />
          </Space.Compact>
        </Space>
      }
    >
      <Table
        rowKey="id"
        columns={columns}
        dataSource={rows}
        loading={loading}
        pagination={pagination}
      />

      <Drawer
        title={detail ? `任务 ${detail.id.slice(0, 13)}…` : "任务详情"}
        width={Math.min(680, window.innerWidth - 32)}
        open={detailOpen}
        onClose={() => {
          setDetailOpen(false);
          detailJobId.current = null;
        }}
        destroyOnClose
        extra={
          detail && (
            <Space>
              {writable && detail.status === "failed" && (
                <Popconfirm title="确认重投该失败任务？" onConfirm={() => void doRetry(detail)}>
                  <Button size="small">重试</Button>
                </Popconfirm>
              )}
              {writable && (detail.status === "pending" || detail.status === "running") && (
                <Popconfirm title="确认取消该任务？" onConfirm={() => void doCancel(detail)}>
                  <Button size="small" danger>取消</Button>
                </Popconfirm>
              )}
            </Space>
          )
        }
      >
        {detail && (
          <>
            <Descriptions column={2} size="small" bordered>
              <Descriptions.Item label="状态">{jobStatusTag(detail.status)}</Descriptions.Item>
              <Descriptions.Item label="类型">{detail.job_type}</Descriptions.Item>
              <Descriptions.Item label="文档 ID">
                <Typography.Text copyable style={{ fontSize: 12 }}>
                  {detail.doc_id ?? "—"}
                </Typography.Text>
              </Descriptions.Item>
              <Descriptions.Item label="Celery 任务">
                {detail.celery_task_id ? detail.celery_task_id.slice(0, 13) + "…" : "—"}
              </Descriptions.Item>
              <Descriptions.Item label="耗时">
                {duration(detail.started_at, detail.finished_at)}
              </Descriptions.Item>
              <Descriptions.Item label="创建时间">
                {new Date(detail.created_at).toLocaleString("zh-CN")}
              </Descriptions.Item>
              {detail.error_message && (
                <Descriptions.Item label="错误" span={2}>
                  <Typography.Text type="danger">{detail.error_message}</Typography.Text>
                </Descriptions.Item>
              )}
            </Descriptions>

            <Typography.Title level={5} style={{ marginTop: 24 }}>
              步骤时间线
            </Typography.Title>
            <Spin spinning={stepsLoading}>
              <Steps
                direction="vertical"
                size="small"
                items={steps.map((s) => ({
                  title: `${s.step_order}. ${s.step_name}`,
                  status: stepStatus(s.status),
                  description: (
                    <div style={{ fontSize: 12 }}>
                      <Space wrap size={4}>
                        <Tag>{s.status}</Tag>
                        {s.duration_ms !== null && <Tag>{s.duration_ms} ms</Tag>}
                      </Space>
                      {s.error_message && (
                        <Typography.Paragraph type="danger" style={{ marginBottom: 0 }}>
                          {s.error_message}
                        </Typography.Paragraph>
                      )}
                      {s.output && (
                        <Typography.Paragraph
                          type="secondary"
                          style={{ marginBottom: 0 }}
                          ellipsis={{ rows: 2, expandable: true, symbol: "展开" }}
                        >
                          {JSON.stringify(s.output)}
                        </Typography.Paragraph>
                      )}
                    </div>
                  ),
                }))}
              />
            </Spin>
          </>
        )}
      </Drawer>
    </Card>
  );
}
