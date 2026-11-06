/**
 * L4 · 质量看板：文档质量检查结果（按版本）+ 评估历史 + 发起评估 + 报告视图。
 * 指标均为「风险/得分」口径：质量分数越低越好，检索指标越高越好。
 */
import { useCallback, useEffect, useState } from "react";
import {
  Button,
  Card,
  Col,
  Descriptions,
  Drawer,
  Empty,
  Form,
  Input,
  InputNumber,
  message,
  Modal,
  Row,
  Select,
  Space,
  Statistic,
  Table,
  Tag,
  Typography,
} from "antd";
import {
  qualityApi,
  errorMessage,
  type QualityCheckOut,
  type EvaluationSummary,
  type EvaluationReport,
} from "../api";

const CHECK_LABELS: Record<string, string> = {
  empty_ratio: "空块率",
  duplicate_ratio: "重复率",
  length_spread: "长度离散",
};

function scoreTag(score: number) {
  // 风险口径：<0.1 健康，<0.3 关注，≥0.3 风险
  const color = score < 0.1 ? "green" : score < 0.3 ? "orange" : "red";
  return <Tag color={color}>{score.toFixed(2)}</Tag>;
}

// ---- Tab 1 · 文档质量 ----

function DocumentQualityCard() {
  const [docId, setDocId] = useState("");
  const [rows, setRows] = useState<QualityCheckOut[] | null>(null);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    if (!docId.trim()) {
      message.warning("请输入文档 ID");
      return;
    }
    setLoading(true);
    try {
      setRows(await qualityApi.byDocument(docId.trim()));
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card
      size="small"
      title="文档质量检查（按版本）"
      extra={
        <Space>
          <Input
            style={{ width: 320 }}
            placeholder="粘贴文档 ID（documents.id）"
            value={docId}
            onChange={(e) => setDocId(e.target.value)}
            onPressEnter={() => void load()}
          />
          <Button type="primary" loading={loading} onClick={() => void load()}>
            查询
          </Button>
        </Space>
      }
    >
      {rows === null ? (
        <Empty description="输入文档 ID 查看空块率 / 重复率 / 长度离散度" />
      ) : rows.length === 0 ? (
        <Empty description="该文档暂无质量检查记录（摄取完成后自动生成）" />
      ) : (
        <Table<QualityCheckOut>
          rowKey={(r) => `${r.version}-${r.check_type}`}
          size="small"
          pagination={false}
          dataSource={rows}
          columns={[
            { title: "版本", dataIndex: "version", width: 70 },
            {
              title: "检查项",
              dataIndex: "check_type",
              width: 110,
              render: (t: string) => CHECK_LABELS[t] ?? t,
            },
            {
              title: "得分（风险，越低越好）",
              dataIndex: "score",
              width: 160,
              render: (s: number) => scoreTag(s),
            },
            {
              title: "原始数据",
              dataIndex: "detail",
              render: (d: Record<string, unknown> | null) => (
                <Typography.Text code style={{ fontSize: 12 }}>
                  {JSON.stringify(d)}
                </Typography.Text>
              ),
            },
            {
              title: "检查时间",
              dataIndex: "created_at",
              width: 170,
              render: (t: string | null) => t?.slice(0, 19).replace("T", " ") ?? "-",
            },
          ]}
        />
      )}
    </Card>
  );
}

// ---- Tab 2 · 评估 ----

const DATASET_PLACEHOLDER = `[
  {"query": "报销流程是什么", "expected_doc_ids": "<文档ID>"},
  {"query": "年假几天", "expected_doc_ids": ["<文档ID>", "<文档ID2>"]}
]`;

function EvaluationCard() {
  const [runs, setRuns] = useState<EvaluationSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(false);
  const [runOpen, setRunOpen] = useState(false);
  const [rerunParent, setRerunParent] = useState<string | null>(null);
  const [form] = Form.useForm();
  const [report, setReport] = useState<EvaluationReport | null>(null);

  const load = useCallback(async (p: number) => {
    setLoading(true);
    try {
      const r = await qualityApi.listEvaluations({ page: p, page_size: 10 });
      setRuns(r.items);
      setTotal(r.total);
      setPage(p);
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(1);
  }, [load]);

  const onRun = async () => {
    let dataset: Array<{ query: string; expected_doc_ids: string[] }>;
    const raw = (form.getFieldValue("dataset") as string) ?? "";
    try {
      const parsed = JSON.parse(raw) as Array<{
        query: string;
        expected_doc_ids: string | string[];
      }>;
      dataset = parsed.map((item) => ({
        query: String(item.query ?? ""),
        expected_doc_ids: Array.isArray(item.expected_doc_ids)
          ? item.expected_doc_ids.map(String)
          : [String(item.expected_doc_ids)],
      }));
      if (dataset.length === 0) throw new Error("数据集为空");
    } catch {
      message.error("数据集 JSON 解析失败，请检查格式（至少一条）");
      return;
    }
    const topK = Number(form.getFieldValue("top_k") ?? 5);
    try {
      const report = await qualityApi.runEvaluation({
        name: String(form.getFieldValue("name") ?? "未命名评估"),
        top_k: topK,
        dataset,
        ...(rerunParent ? { parent_run_id: rerunParent } : {}),
      });
      message.success(`评估完成：recall@k=${report.metrics?.["recall@k"] ?? "-"}`);
      setRunOpen(false);
      setRerunParent(null);
      setReport(report);
      void load(1);
    } catch (err) {
      message.error(errorMessage(err));
    }
  };

  const openReport = async (runId: string) => {
    try {
      setReport(await qualityApi.evaluation(runId));
    } catch (err) {
      message.error(errorMessage(err));
    }
  };

  /** 方案 A（L4.1）：沿用原名称 + parent_run_id 溯源，重跑生成新行。
   * 名字不再拼 -rerun 后缀——区分靠「↻ 重跑」徽标与 created_at。 */
  const openRerun = (r: EvaluationReport) => {
    form.setFieldsValue({
      name: r.name,
      top_k: r.metrics?.top_k ?? 5,
      dataset: JSON.stringify(r.dataset, null, 2),
    });
    setRerunParent(r.id);
    setRunOpen(true);
  };

  const onReview = async (
    index: number,
    verdict: "correct" | "false_positive" | "missed",
  ) => {
    if (!report) return;
    try {
      const updated = await qualityApi.reviewResult(report.id, index, { verdict });
      setReport(updated);
      message.success(`已标注第 ${index + 1} 条：${verdict}`);
    } catch (err) {
      message.error(errorMessage(err));
    }
  };

  const m = report?.metrics ?? null;

  return (
    <Card
      size="small"
      title="检索评估"
      extra={
        <Button type="primary" onClick={() => setRunOpen(true)}>
          新建评估
        </Button>
      }
    >
      <Table<EvaluationSummary>
        rowKey="id"
        size="small"
        loading={loading}
        dataSource={runs}
        pagination={{ current: page, total, pageSize: 10, onChange: (p) => void load(p) }}
        columns={[
          {
            title: "名称",
            dataIndex: "name",
            ellipsis: true,
            render: (n: string, r) => (
              <Space size={4}>
                <span>{n}</span>
                {r.parent_run_id && <Tag color="purple">↻ 重跑</Tag>}
              </Space>
            ),
          },
          { title: "查询数", dataIndex: "queries", width: 80 },
          {
            title: "recall@k",
            width: 100,
            render: (_, r) => r.metrics?.["recall@k"]?.toFixed(4) ?? "-",
          },
          {
            title: "MRR",
            width: 90,
            render: (_, r) => r.metrics?.mrr?.toFixed(4) ?? "-",
          },
          {
            title: "nDCG@k",
            width: 90,
            render: (_, r) => r.metrics?.["ndcg@k"]?.toFixed(4) ?? "-",
          },
          {
            title: "hit_rate",
            width: 90,
            render: (_, r) => r.metrics?.hit_rate?.toFixed(4) ?? "-",
          },
          {
            title: "时间",
            dataIndex: "created_at",
            width: 160,
            render: (t: string | null) => t?.slice(0, 19).replace("T", " ") ?? "-",
          },
          {
            title: "操作",
            width: 90,
            render: (_, r) => (
              <Button size="small" type="link" onClick={() => void openReport(r.id)}>
                报告
              </Button>
            ),
          },
        ]}
      />

      <Modal
        title={rerunParent ? "编辑并重跑（生成新评估）" : "新建检索评估"}
        open={runOpen}
        onOk={() => void onRun()}
        onCancel={() => {
          setRunOpen(false);
          setRerunParent(null);
        }}
        width={640}
        destroyOnClose
      >
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="评估名称" rules={[{ required: true }]}>
            <Input placeholder="例如：hr-suite 回归" />
          </Form.Item>
          <Form.Item name="top_k" label="top_k" initialValue={5}>
            <InputNumber min={1} max={20} style={{ width: 120 }} />
          </Form.Item>
          <Form.Item
            name="dataset"
            label="数据集（JSON：query + expected_doc_ids）"
            rules={[{ required: true }]}
          >
            <Input.TextArea rows={8} placeholder={DATASET_PLACEHOLDER} />
          </Form.Item>
        </Form>
      </Modal>

      <Drawer
        title={
          report ? (
            <Space size={6}>
              <span>评估报告：{report.name}</span>
              {report.parent_run_id && <Tag color="purple">↻ 重跑</Tag>}
            </Space>
          ) : (
            ""
          )
        }
        open={report !== null}
        onClose={() => setReport(null)}
        width={720}
        extra={
          report && (
            <Button type="primary" onClick={() => openRerun(report)}>
              编辑并重跑（生成新评估）
            </Button>
          )
        }
      >
        {report && m && (
          <>
            <Row gutter={16}>
              <Col span={6}>
                <Statistic title="recall@k" value={m["recall@k"] ?? 0} precision={4} />
              </Col>
              <Col span={6}>
                <Statistic title="MRR" value={m.mrr ?? 0} precision={4} />
              </Col>
              <Col span={6}>
                <Statistic title="nDCG@k" value={m["ndcg@k"] ?? 0} precision={4} />
              </Col>
              <Col span={6}>
                <Statistic title="hit_rate" value={m.hit_rate ?? 0} precision={4} />
              </Col>
            </Row>
            <Descriptions size="small" column={2} style={{ marginTop: 16 }}>
              <Descriptions.Item label="查询数">{m.queries}</Descriptions.Item>
              <Descriptions.Item label="top_k">{m.top_k}</Descriptions.Item>
            </Descriptions>

            <Typography.Title level={5} style={{ marginTop: 16 }}>
              评估集（本次输入，可在上方「编辑并重跑」中修改）
            </Typography.Title>
            <Table
              rowKey={(r) => r.query}
              size="small"
              pagination={false}
              dataSource={report.dataset}
              columns={[
                { title: "查询", dataIndex: "query", ellipsis: true },
                {
                  title: "期望命中文档",
                  dataIndex: "expected_doc_ids",
                  render: (ids: string[]) => (
                    <Typography.Text code style={{ fontSize: 12 }}>
                      {ids.join(", ")}
                    </Typography.Text>
                  ),
                },
              ]}
            />

            <Typography.Title level={5} style={{ marginTop: 16 }}>
              逐条结果与人工审核
            </Typography.Title>
            <Table
              rowKey={(r) => r.query}
              size="small"
              style={{ marginTop: 16 }}
              pagination={false}
              dataSource={report.result ?? []}
              columns={[
                { title: "查询", dataIndex: "query", ellipsis: true },
                {
                  title: "首命中位",
                  dataIndex: "first_hit_rank",
                  width: 90,
                  render: (v: number) => (v > 0 ? v : <Tag color="red">未命中</Tag>),
                },
                {
                  title: "RR",
                  dataIndex: "reciprocal_rank",
                  width: 70,
                  render: (v: number) => v.toFixed(2),
                },
                {
                  title: "命中文档",
                  dataIndex: "hit_doc_ids",
                  render: (ids: string[]) =>
                    ids.length ? (
                      <Typography.Text code style={{ fontSize: 12 }}>
                        {ids.join(", ")}
                      </Typography.Text>
                    ) : (
                      "-"
                    ),
                },
                {
                  title: "人工审核",
                  key: "review",
                  width: 150,
                  render: (_: unknown, __: unknown, index: number) => {
                    const current = report?.result?.[index]?.review?.verdict;
                    return (
                      <Select
                        size="small"
                        style={{ width: 130 }}
                        value={(current as string) ?? "correct"}
                        onChange={(v: unknown) =>
                          void onReview(
                            index,
                            v as "correct" | "false_positive" | "missed",
                          )
                        }
                        options={[
                          { value: "correct", label: "✓ 正确" },
                          { value: "false_positive", label: "✗ 误检" },
                          { value: "missed", label: "△ 漏检" },
                        ]}
                      />
                    );
                  },
                },
              ]}
            />
          </>
        )}
      </Drawer>
    </Card>
  );
}

// ---- page ----

export default function QualityPage() {
  return (
    <Card title="质量与评估">
      <Space direction="vertical" style={{ width: "100%" }} size="middle">
        <DocumentQualityCard />
        <EvaluationCard />
      </Space>
    </Card>
  );
}
