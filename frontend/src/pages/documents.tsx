/**
 * H2 · 文档管理页：列表（分页/筛选/搜索）+ 拖拽上传（进度/类型校验）
 * + 详情抽屉（基础信息/版本信息）+ Chunk 预览（分页/高亮）+ 重处理/软删除。
 */
import { useCallback, useEffect, useRef, useState } from "react";
import {
  Button,
  Card,
  Drawer,
  Descriptions,
  Input,
  List,
  message,
  Popconfirm,
  Progress,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  Upload,
} from "antd";
import type { ColumnsType, TablePaginationConfig } from "antd/es/table";
import {
  CloudUploadOutlined,
  ReloadOutlined,
  SearchOutlined,
} from "@ant-design/icons";
import {
  documentsApi,
  errorMessage,
  type ChunkOut,
  type DocumentDetail,
  type DocumentOut,
} from "../api";

const ACCEPT = [".pdf", ".docx", ".txt"];
const MAX_MB = 50;

function fileOk(name: string): boolean {
  const lower = name.toLowerCase();
  return ACCEPT.some((ext) => lower.endsWith(ext));
}

function statusTag(status: string) {
  const map: Record<string, { color: string; text: string }> = {
    processing: { color: "processing", text: "处理中" },
    parsed: { color: "success", text: "已解析" },
    failed: { color: "error", text: "失败" },
    deleted: { color: "default", text: "已删除" },
  };
  const conf = map[status] ?? { color: "default", text: status };
  return <Tag color={conf.color}>{conf.text}</Tag>;
}

interface UploadState {
  name: string;
  percent: number;
}

export default function DocumentsPage() {
  // ---- list state ----
  const [rows, setRows] = useState<DocumentOut[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [status, setStatus] = useState<string | undefined>();
  const [fileType, setFileType] = useState<string | undefined>();
  const [keyword, setKeyword] = useState("");
  const [loading, setLoading] = useState(false);

  // ---- upload state ----
  const [upload, setUpload] = useState<UploadState | null>(null);

  // ---- detail drawer state ----
  const [detail, setDetail] = useState<DocumentDetail | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);

  // ---- chunk preview state ----
  const [chunks, setChunks] = useState<ChunkOut[]>([]);
  const [chunkTotal, setChunkTotal] = useState(0);
  const [chunkPage, setChunkPage] = useState(1);
  const [chunksLoading, setChunksLoading] = useState(false);

  const abortRef = useRef<AbortController | null>(null);

  const fetchList = useCallback(async () => {
    setLoading(true);
    try {
      const result = await documentsApi.list({
        page,
        page_size: pageSize,
        status,
        file_type: fileType,
        keyword: keyword || undefined,
      });
      setRows(result.items);
      setTotal(result.total);
    } catch (err) {
      message.error(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [page, pageSize, status, fileType, keyword]);

  useEffect(() => {
    void fetchList();
  }, [fetchList]);

  const fetchChunks = useCallback(
    async (docId: string, p: number) => {
      setChunksLoading(true);
      try {
        const result = await documentsApi.chunks(docId, { page: p, page_size: 10 });
        setChunks(result.items);
        setChunkTotal(result.total);
      } catch (err) {
        message.error(errorMessage(err));
      } finally {
        setChunksLoading(false);
      }
    },
    [],
  );

  const openDetail = async (docId: string) => {
    try {
      const d = await documentsApi.detail(docId);
      setDetail(d);
      setDetailOpen(true);
      setChunkPage(1);
      void fetchChunks(docId, 1);
    } catch (err) {
      message.error(errorMessage(err));
    }
  };

  const doUpload = async (file: File) => {
    if (!fileOk(file.name)) {
      message.error(`仅支持 ${ACCEPT.join(" / ")} 文件`);
      return;
    }
    if (file.size > MAX_MB * 1024 * 1024) {
      message.error(`文件超过 ${MAX_MB} MB 上限`);
      return;
    }
    setUpload({ name: file.name, percent: 0 });
    const controller = new AbortController();
    abortRef.current = controller;
    try {
      const form = new FormData();
      form.append("file", file);
      const result = await documentsApi.uploadWithProgress(form, (percent) => {
        setUpload((prev) => (prev ? { ...prev, percent } : prev));
      }, controller.signal);
      message.success(
        result.duplicate
          ? `重复文件命中幂等（doc 已存在，job=${result.job_id.slice(0, 8)}…）`
          : `上传成功，已投递流水线（job=${result.job_id.slice(0, 8)}…）`,
      );
      setPage(1);
      void fetchList();
    } catch (err) {
      if (!controller.signal.aborted) message.error(errorMessage(err));
    } finally {
      setUpload(null);
      abortRef.current = null;
    }
  };

  const doReprocess = async (doc: DocumentOut) => {
    try {
      const result = await documentsApi.reprocess(doc.id);
      message.success(`已创建重处理任务（job=${result.job_id.slice(0, 8)}…）`);
    } catch (err) {
      message.error(errorMessage(err));
    }
  };

  const doDelete = async (doc: DocumentOut) => {
    try {
      await documentsApi.remove(doc.id);
      message.success(`已软删除：${doc.title}`);
      void fetchList();
    } catch (err) {
      message.error(errorMessage(err));
    }
  };

  const columns: ColumnsType<DocumentOut> = [
    { title: "标题", dataIndex: "title", ellipsis: true },
    { title: "文件名", dataIndex: "file_name", ellipsis: true },
    {
      title: "类型",
      dataIndex: "file_type",
      width: 80,
      render: (t: string) => <Tag>{t.toUpperCase()}</Tag>,
    },
    { title: "状态", dataIndex: "status", width: 100, render: statusTag },
    { title: "版本", dataIndex: "current_version", width: 70 },
    { title: "创建时间", dataIndex: "created_at", width: 170,
      render: (v: string) => new Date(v).toLocaleString("zh-CN") },
    {
      title: "操作",
      key: "actions",
      width: 230,
      render: (_, doc) => (
        <Space>
          <Button size="small" onClick={() => void openDetail(doc.id)}>详情</Button>
          <Button size="small" icon={<ReloadOutlined />} onClick={() => void doReprocess(doc)}>
            重新处理
          </Button>
          <Popconfirm
            title="确认软删除该文档？"
            onConfirm={() => void doDelete(doc)}
          >
            <Button size="small" danger>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const pagination: TablePaginationConfig = {
    current: page,
    pageSize,
    total,
    showSizeChanger: true,
    showTotal: (t) => `共 ${t} 篇`,
    onChange: (p, ps) => {
      setPage(p);
      setPageSize(ps);
    },
  };

  return (
    <Card
      title="文档管理"
      extra={
        <Space wrap>
          <Input
            allowClear
            prefix={<SearchOutlined />}
            placeholder="按标题 / 文件名搜索"
            style={{ width: 220 }}
            onChange={(e) => {
              setKeyword(e.target.value);
              setPage(1);
            }}
          />
          <Select
            allowClear
            placeholder="状态"
            style={{ width: 120 }}
            options={[{ value: "processing", label: "处理中" }]}
            onChange={(v) => {
              setStatus(v);
              setPage(1);
            }}
          />
          <Select
            allowClear
            placeholder="类型"
            style={{ width: 110 }}
            options={[
              { value: "pdf", label: "PDF" },
              { value: "docx", label: "DOCX" },
              { value: "txt", label: "TXT" },
            ]}
            onChange={(v) => {
              setFileType(v);
              setPage(1);
            }}
          />
        </Space>
      }
    >
      <Upload.Dragger
        accept={ACCEPT.join(",")}
        multiple={false}
        showUploadList={false}
        customRequest={({ file }) => void doUpload(file as File)}
        style={{ marginBottom: 16 }}
      >
        <p className="ant-upload-drag-icon">
          <CloudUploadOutlined />
        </p>
        <p className="ant-upload-text">点击或拖拽文件到此处上传（pdf / docx / txt，≤ {MAX_MB} MB）</p>
        <p className="ant-upload-hint">相同内容重复上传会命中幂等，不会产生新版本</p>
      </Upload.Dragger>

      {upload && (
        <div style={{ marginBottom: 16 }}>
          <Typography.Text type="secondary">{upload.name}</Typography.Text>
          <Progress percent={upload.percent} status="active" />
        </div>
      )}

      <Table
        rowKey="id"
        columns={columns}
        dataSource={rows}
        loading={loading}
        pagination={pagination}
      />

      <Drawer
        title={detail?.title ?? "文档详情"}
        width={Math.min(640, window.innerWidth - 32)}
        open={detailOpen}
        onClose={() => setDetailOpen(false)}
        destroyOnClose
      >
        {detail && (
          <>
            <Descriptions column={2} size="small" bordered>
              <Descriptions.Item label="文档 ID" span={2}>
                <Typography.Text copyable>{detail.id}</Typography.Text>
              </Descriptions.Item>
              <Descriptions.Item label="文件名">{detail.file_name}</Descriptions.Item>
              <Descriptions.Item label="类型">
                {detail.file_type.toUpperCase()}
              </Descriptions.Item>
              <Descriptions.Item label="状态">{statusTag(detail.status)}</Descriptions.Item>
              <Descriptions.Item label="当前版本">{detail.current_version}</Descriptions.Item>
              <Descriptions.Item label="创建时间">
                {new Date(detail.created_at).toLocaleString("zh-CN")}
              </Descriptions.Item>
              <Descriptions.Item label="更新时间">
                {new Date(detail.updated_at).toLocaleString("zh-CN")}
              </Descriptions.Item>
              {detail.latest_version && (
                <>
                  <Descriptions.Item label="版本号">
                    v{detail.latest_version.version}（latest）
                  </Descriptions.Item>
                  <Descriptions.Item label="解析状态">
                    {statusTag(detail.latest_version.parse_status)}
                  </Descriptions.Item>
                  <Descriptions.Item label="文件大小" span={2}>
                    {(detail.latest_version.file_size / 1024).toFixed(1)} KB
                  </Descriptions.Item>
                  <Descriptions.Item label="内容哈希" span={2}>
                    <Typography.Text copyable style={{ fontSize: 12 }}>
                      {detail.latest_version.content_hash}
                    </Typography.Text>
                  </Descriptions.Item>
                </>
              )}
            </Descriptions>

            <Typography.Title level={5} style={{ marginTop: 24 }}>
              Chunk 预览（共 {chunkTotal} 条）
            </Typography.Title>
            <List
              loading={chunksLoading}
              dataSource={chunks}
              pagination={{
                current: chunkPage,
                pageSize: 10,
                total: chunkTotal,
                size: "small",
                onChange: (p) => {
                  setChunkPage(p);
                  if (detail) void fetchChunks(detail.id, p);
                },
              }}
              renderItem={(c) => (
                <List.Item>
                  <div style={{ width: "100%" }}>
                    <Space style={{ marginBottom: 4 }}>
                      <Tag color="blue">chunk #{c.chunk_index}</Tag>
                      {c.page !== null && <Tag color="geekblue">第 {c.page} 页</Tag>}
                      <Tag>{c.token_count} tokens</Tag>
                    </Space>
                    <Typography.Paragraph
                      style={{ marginBottom: 0, whiteSpace: "pre-wrap" }}
                      ellipsis={{ rows: 4, expandable: true, symbol: "展开" }}
                    >
                      {c.text}
                    </Typography.Paragraph>
                  </div>
                </List.Item>
              )}
            />
          </>
        )}
      </Drawer>
    </Card>
  );
}
