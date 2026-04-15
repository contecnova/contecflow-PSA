export function getFirstIssueByField(error) {
  const fieldErrors = {}

  error.issues.forEach(issue => {
    const field = issue.path?.[0]
    if (field && !fieldErrors[field]) {
      fieldErrors[field] = issue.message
    }
  })

  return fieldErrors
}

export function validateSchema(schema, values) {
  const parsed = schema.safeParse(values)

  if (parsed.success) {
    return { success: true, data: parsed.data, errors: {} }
  }

  return {
    success: false,
    data: null,
    errors: getFirstIssueByField(parsed.error),
  }
}

export function getFieldErrorStyle(baseStyle, hasError) {
  if (!hasError) return baseStyle

  return {
    ...baseStyle,
    border: '1px solid var(--danger)',
    boxShadow: '0 0 0 1px rgba(255, 71, 87, 0.18)',
  }
}