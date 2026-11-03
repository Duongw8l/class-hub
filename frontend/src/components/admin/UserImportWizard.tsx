import { useState } from 'react'
import type { CreatedCredential, UserImportPreview } from '../../api/admin'
import { ApiError } from '../../api/client'
import { useConfirmUserImport, usePreviewUserImport } from '../../hooks/useAdmin'
import { FilePicker } from '../import/FilePicker'
import { Stepper } from '../import/Stepper'

function errorText(error: unknown): string {
  if (error instanceof ApiError) return error.message
  return 'Không kết nối được tới máy chủ. Hãy kiểm tra back-end đã chạy chưa.'
}

const NONE = ''

// Sinh CSV (có BOM UTF-8 để Excel đọc đúng dấu) gồm email và mật khẩu tạm, rồi tải về.
function downloadCredentialsCsv(credentials: CreatedCredential[]): void {
  const escape = (value: string) => `"${value.replace(/"/g, '""')}"`
  const header = ['Họ và tên', 'Email', 'Vai trò', 'Mật khẩu tạm']
  const lines = [
    header.map(escape).join(','),
    ...credentials.map((c) =>
      [c.full_name, c.email, c.role_label, c.temporary_password].map(escape).join(','),
    ),
  ]
  const blob = new Blob(['﻿' + lines.join('\r\n')], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = 'mat-khau-tam-giao-vien.csv'
  anchor.click()
  URL.revokeObjectURL(url)
}

// Bảng xem trước gọn cho nhập giáo viên: Họ tên, Email, Vai trò, trạng thái và thông báo lỗi.
function PreviewTable({ preview }: { preview: UserImportPreview }) {
  return (
    <div className="overflow-x-auto">
      <table className="data-table min-w-full">
        <thead>
          <tr>
            <th className="w-16">Dòng</th>
            <th>Họ và tên</th>
            <th>Email</th>
            <th>Vai trò</th>
            <th>Ghi chú</th>
          </tr>
        </thead>
        <tbody>
          {preview.rows.map((row) => (
            <tr key={row.line} className={row.status === 'error' ? 'bg-red-50' : undefined}>
              <td className="tabular-nums">{row.line}</td>
              <td>{row.full_name ?? '—'}</td>
              <td>{row.email ?? '—'}</td>
              <td>{row.role_label ?? '—'}</td>
              <td className={row.status === 'error' ? 'text-red-700' : 'text-slate-600'}>
                {row.messages.length > 0
                  ? row.messages.map((m) => m.message).join(' ')
                  : row.action === 'new'
                    ? 'Sẽ tạo mới'
                    : ''}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// Chọn cột của tệp cho từng trường (mở sẵn khi còn thiếu cột bắt buộc).
function ColumnMapping({
  preview,
  pending,
  onApply,
}: {
  preview: UserImportPreview
  pending: boolean
  onApply: (mapping: Record<string, string | null>, headerRow?: number) => void
}) {
  const missing = preview.missing_required.length > 0
  const [mapping, setMapping] = useState<Record<string, string>>(() =>
    Object.fromEntries(preview.fields.map((field) => [field.name, field.column ?? NONE])),
  )
  const [headerRow, setHeaderRow] = useState(String(preview.header_line))

  function apply() {
    const row = Number.parseInt(headerRow, 10)
    onApply(
      Object.fromEntries(
        Object.entries(mapping).map(([field, column]) => [field, column === NONE ? null : column]),
      ),
      Number.isInteger(row) && row >= 1 ? row : undefined,
    )
  }

  return (
    <details open={missing} className="card p-4">
      <summary className="cursor-pointer font-medium">
        Cột của tệp
        {missing && (
          <span className="ml-2 rounded-full bg-red-100 px-2 py-0.5 text-sm text-red-700">
            Còn thiếu {preview.missing_required.length} cột bắt buộc
          </span>
        )}
      </summary>
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        {preview.fields.map((field) => (
          <label key={field.name} className="block text-sm font-medium text-slate-700">
            {field.label}
            {field.required && <span className="text-red-600"> *</span>}
            <select
              value={mapping[field.name] ?? NONE}
              disabled={pending}
              onChange={(event) =>
                setMapping((current) => ({ ...current, [field.name]: event.target.value }))
              }
              className="input mt-1"
            >
              <option value={NONE}>— Không dùng —</option>
              {preview.detected_columns.map((column) => (
                <option key={column} value={column}>
                  {column}
                </option>
              ))}
            </select>
          </label>
        ))}
        <label className="block text-sm font-medium text-slate-700">
          Dòng tiêu đề
          <input
            type="number"
            min={1}
            value={headerRow}
            disabled={pending}
            onChange={(event) => setHeaderRow(event.target.value)}
            className="input mt-1"
          />
        </label>
      </div>
      <button type="button" onClick={apply} disabled={pending} className="btn-secondary mt-4">
        Áp dụng cách chọn cột
      </button>
    </details>
  )
}

// Trình nhập giáo viên từ tệp (chỉ Admin): chọn tệp → xem trước (chưa tạo gì) → xác nhận → hiện mật
// khẩu tạm một lần kèm nút tải CSV. Tệp được giữ trong bộ nhớ để gửi lại khi đổi cách chọn cột.
export function UserImportWizard({ onDone }: { onDone?: () => void }) {
  const previewMutation = usePreviewUserImport()
  const confirmMutation = useConfirmUserImport()
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<UserImportPreview | null>(null)
  const [credentials, setCredentials] = useState<CreatedCredential[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  const busy = previewMutation.isPending || confirmMutation.isPending

  function runPreview(picked: File, mapping?: Record<string, string | null>, headerRow?: number) {
    setCredentials(null)
    previewMutation.mutate(
      { file: picked, mapping, headerRow },
      {
        onSuccess: (data) => {
          setPreview(data)
          setError(null)
        },
        onError: (caught) => setError(errorText(caught)),
      },
    )
  }

  function pickFile(picked: File) {
    setFile(picked)
    runPreview(picked)
  }

  function reset() {
    setFile(null)
    setPreview(null)
    setCredentials(null)
    setError(null)
  }

  function confirm() {
    if (!preview?.job_id) return
    confirmMutation.mutate(preview.job_id, {
      onSuccess: (data) => {
        setCredentials(data.credentials)
        setError(null)
        onDone?.()
      },
      onError: (caught) => setError(errorText(caught)),
    })
  }

  if (credentials) {
    return (
      <div className="space-y-4">
        <Stepper current={4} />
        <section
          aria-labelledby="ket-qua-nhap-gv"
          className="space-y-4 rounded-2xl border border-amber-300 bg-amber-50 p-5 text-amber-900"
        >
          <h3 id="ket-qua-nhap-gv" className="text-base font-semibold">
            Đã tạo {credentials.length} tài khoản
          </h3>
          <p className="text-sm">
            Mật khẩu tạm dưới đây <strong>chỉ hiện một lần</strong>, hệ thống không lưu bản đọc được.
            Hãy tải CSV hoặc sao chép, đưa cho giáo viên, và nhắc họ đổi mật khẩu khi đăng nhập lần
            đầu (menu người dùng › Đổi mật khẩu).
          </p>
          <div className="overflow-x-auto">
            <table className="data-table min-w-full">
              <thead>
                <tr>
                  <th>Họ và tên</th>
                  <th>Email</th>
                  <th>Vai trò</th>
                  <th>Mật khẩu tạm</th>
                </tr>
              </thead>
              <tbody>
                {credentials.map((c) => (
                  <tr key={c.email}>
                    <td>{c.full_name}</td>
                    <td>{c.email}</td>
                    <td>{c.role_label}</td>
                    <td>
                      <code className="select-all font-mono tracking-wider">
                        {c.temporary_password}
                      </code>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="flex flex-wrap gap-3">
            <button
              type="button"
              onClick={() => downloadCredentialsCsv(credentials)}
              className="btn-primary"
            >
              Tải CSV mật khẩu tạm
            </button>
            <button type="button" onClick={reset} className="btn-secondary">
              Nhập tệp khác
            </button>
          </div>
        </section>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <Stepper current={confirmMutation.isPending ? 3 : preview ? 2 : 1} />
      <p className="text-sm text-slate-600">
        Tệp .xlsx hoặc .csv (UTF-8), mỗi dòng một giáo viên, gồm cột <strong>Họ và tên</strong> và{' '}
        <strong>Email</strong> (bắt buộc) cùng <strong>Vai trò</strong> (tuỳ chọn: "Giáo viên" hoặc
        "Ban giám hiệu"; để trống là Giáo viên). Mỗi tài khoản được cấp một mật khẩu tạm ngẫu nhiên.
        Email đã có tài khoản sẽ bị báo lỗi (chỉ tạo tài khoản mới).
      </p>

      <FilePicker file={file} onPick={pickFile} disabled={busy} />

      {previewMutation.isPending && (
        <p aria-live="polite" className="text-sm text-slate-600">
          Đang đọc và kiểm tra tệp…
        </p>
      )}
      {error !== null && (
        <p role="alert" className="rounded-xl bg-red-50 p-3 text-sm text-red-800 ring-1 ring-red-200">
          {error}
        </p>
      )}

      {preview && (
        <section aria-labelledby="xem-truoc-gv" className="space-y-4">
          <h3 id="xem-truoc-gv" className="text-base font-medium">
            Xem trước: {preview.file_name}
          </h3>
          {preview.notes.length > 0 && (
            <ul className="space-y-1 rounded-xl bg-amber-50 p-3 text-sm text-amber-900 ring-1 ring-amber-200">
              {preview.notes.map((note) => (
                <li key={note}>{note}</li>
              ))}
            </ul>
          )}

          <ColumnMapping
            key={`${preview.file_name}|${preview.header_line}|${preview.fields.map((f) => f.column).join('|')}`}
            preview={preview}
            pending={busy}
            onApply={(mapping, headerRow) => file && runPreview(file, mapping, headerRow)}
          />

          {preview.missing_required.length === 0 && (
            <>
              <dl className="grid grid-cols-3 gap-3">
                <div className="card p-3">
                  <dt className="text-xs text-slate-500">Tổng số dòng</dt>
                  <dd className="text-2xl font-semibold tabular-nums">{preview.summary.total_rows}</dd>
                </div>
                <div className="card p-3">
                  <dt className="text-xs text-slate-500">Dòng lỗi</dt>
                  <dd className="text-2xl font-semibold tabular-nums text-red-700">
                    {preview.summary.error_rows}
                  </dd>
                </div>
                <div className="card p-3">
                  <dt className="text-xs text-slate-500">Sẽ tạo mới</dt>
                  <dd className="text-2xl font-semibold tabular-nums text-green-700">
                    {preview.summary.new_rows}
                  </dd>
                </div>
              </dl>

              {preview.rows.length > 0 ? (
                <PreviewTable preview={preview} />
              ) : (
                <p className="card p-4 text-sm text-slate-600">Không có dòng nào để hiển thị.</p>
              )}
              {preview.truncated && (
                <p className="text-sm text-slate-500">
                  Chỉ hiện một phần các dòng; mọi dòng lỗi luôn có đủ. Khi xác nhận, hệ thống vẫn
                  tạo toàn bộ tài khoản hợp lệ trong tệp.
                </p>
              )}

              <div className="space-y-3 card p-4">
                {preview.summary.error_rows > 0 && (
                  <p role="alert" className="text-sm text-red-700">
                    Tệp còn {preview.summary.error_rows} dòng lỗi nên chưa thể tạo tài khoản. Hãy sửa
                    tệp rồi tải lại; khi còn lỗi hệ thống không tạo gì (kể cả các dòng đúng).
                  </p>
                )}
                {preview.can_confirm && (
                  <p className="text-sm text-slate-600">
                    Sẽ tạo {preview.summary.new_rows} tài khoản. Chưa có gì được tạo cho tới khi bạn
                    xác nhận.
                    {preview.expires_at &&
                      ` Bản xem trước hết hạn lúc ${new Date(preview.expires_at).toLocaleString('vi-VN')}.`}
                  </p>
                )}
                <button
                  type="button"
                  disabled={busy || !preview.can_confirm || preview.job_id === null}
                  onClick={confirm}
                  className="btn-primary"
                >
                  {confirmMutation.isPending ? 'Đang tạo tài khoản…' : 'Xác nhận và tạo tài khoản'}
                </button>
              </div>
            </>
          )}
        </section>
      )}
    </div>
  )
}
