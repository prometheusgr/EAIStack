/**
 * Flags a setState-shaped call (identifier matching /^set[A-Z]/) that appears
 * after an `await` inside an async function, unless it is guarded by
 * `if (isMounted())`.
 *
 * Why this scope: setState calls before the first `await` in a render pass
 * can't race an unmount (the component is still mounted when they run
 * synchronously). Calls after an `await` run in a microtask that may fire
 * after the component has unmounted, updating state on a dead component.
 * See useApiCall/useApiMutation (frontend/src/hooks) for the guarded pattern
 * this rule enforces.
 */

const SETTER_NAME_PATTERN = /^set[A-Z]/
const GLOBAL_NON_SETSTATE_NAMES = new Set(['setTimeout', 'setInterval', 'setImmediate'])

function isSetterCall(node) {
  return (
    node.type === 'CallExpression' &&
    node.callee.type === 'Identifier' &&
    SETTER_NAME_PATTERN.test(node.callee.name) &&
    !GLOBAL_NON_SETSTATE_NAMES.has(node.callee.name)
  )
}

function isIsMountedCall(node) {
  return (
    node.type === 'CallExpression' &&
    node.callee.type === 'Identifier' &&
    node.callee.name === 'isMounted'
  )
}

function testGuardsWithIsMounted(test) {
  if (isIsMountedCall(test)) return true
  if (test.type === 'LogicalExpression' && test.operator === '&&') {
    return testGuardsWithIsMounted(test.left) || testGuardsWithIsMounted(test.right)
  }
  return false
}

function isInsideIsMountedGuard(node, boundaryFunction) {
  let current = node.parent
  while (current && current !== boundaryFunction) {
    if (current.type === 'IfStatement' && testGuardsWithIsMounted(current.test)) {
      return true
    }
    current = current.parent
  }
  return false
}

function findEnclosingAsyncFunction(node) {
  let current = node.parent
  while (current) {
    if (
      (current.type === 'FunctionDeclaration' ||
        current.type === 'FunctionExpression' ||
        current.type === 'ArrowFunctionExpression') &&
      current.async
    ) {
      return current
    }
    current = current.parent
  }
  return null
}

function hasPrecedingAwait(asyncFunctionBody, beforeRangeStart) {
  const stack = [asyncFunctionBody]
  while (stack.length > 0) {
    const current = stack.pop()
    if (!current || typeof current.type !== 'string') continue
    if (current.range[0] >= beforeRangeStart) continue

    if (current.type === 'AwaitExpression') return true

    if (
      current.type === 'FunctionDeclaration' ||
      current.type === 'FunctionExpression' ||
      current.type === 'ArrowFunctionExpression'
    ) {
      continue
    }

    for (const key of Object.keys(current)) {
      if (key === 'parent') continue
      const value = current[key]
      if (Array.isArray(value)) {
        for (const item of value) {
          if (item && typeof item.type === 'string') stack.push(item)
        }
      } else if (value && typeof value.type === 'string') {
        stack.push(value)
      }
    }
  }
  return false
}

module.exports = {
  meta: {
    type: 'problem',
    docs: {
      description:
        'Disallow setState calls after an await unless guarded by if (isMounted())',
    },
    schema: [],
    messages: {
      unguarded:
        "'{{name}}' is called after an await without an isMounted() guard. " +
        'The component may have unmounted by the time this microtask resumes. ' +
        "Wrap it in 'if (isMounted()) {{name}}(...)' (see useApiCall/useApiMutation).",
    },
  },
  create(context) {
    return {
      CallExpression(node) {
        if (!isSetterCall(node)) return

        const asyncFunction = findEnclosingAsyncFunction(node)
        if (!asyncFunction) return

        if (!hasPrecedingAwait(asyncFunction.body, node.range[0])) return
        if (isInsideIsMountedGuard(node, asyncFunction)) return

        context.report({
          node,
          messageId: 'unguarded',
          data: { name: node.callee.name },
        })
      },
    }
  },
}
