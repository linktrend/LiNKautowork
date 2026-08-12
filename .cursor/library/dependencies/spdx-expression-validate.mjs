/**
 * Package-local ESM adaptation of spdx-expression-validate@2.0.0 and its
 * spdx-expression-parse@3.0.1 dependency.  See NOTICE.md for attribution.
 */
import { readFileSync } from 'node:fs'

const packageUrl = (name) => new URL(`./${name}`, import.meta.url)
const readJson = (name) => JSON.parse(readFileSync(packageUrl(name), 'utf8'))
const licenses = [
  ...readJson('spdx-license-ids.json'),
  ...readJson('spdx-license-ids-deprecated.json'),
]
const exceptions = readJson('spdx-exceptions.json')

function scan(source) {
  let index = 0

  const hasMore = () => index < source.length

  function read(value) {
    if (value instanceof RegExp) {
      const chars = source.slice(index)
      const match = chars.match(value)
      if (match) {
        index += match[0].length
        return match[0]
      }
    } else if (source.indexOf(value, index) === index) {
      index += value.length
      return value
    }
  }

  function skipWhitespace() {
    read(/[ ]*/)
  }

  function operator() {
    let string
    const possibilities = ['WITH', 'AND', 'OR', '(', ')', ':', '+']
    for (let i = 0; i < possibilities.length; i += 1) {
      string = read(possibilities[i])
      if (string) break
    }
    if (string === '+' && index > 1 && source[index - 2] === ' ') throw new Error('Space before `+`')
    return string && { type: 'OPERATOR', string }
  }

  function idstring() {
    return read(/[A-Za-z0-9-.]+/)
  }

  function expectIdstring() {
    const string = idstring()
    if (!string) throw new Error(`Expected idstring at offset ${index}`)
    return string
  }

  function documentRef() {
    if (read('DocumentRef-')) return { type: 'DOCUMENTREF', string: expectIdstring() }
  }

  function licenseRef() {
    if (read('LicenseRef-')) return { type: 'LICENSEREF', string: expectIdstring() }
  }

  function identifier() {
    const begin = index
    const string = idstring()
    if (licenses.indexOf(string) !== -1) return { type: 'LICENSE', string }
    if (exceptions.indexOf(string) !== -1) return { type: 'EXCEPTION', string }
    index = begin
  }

  function parseToken() {
    return operator() || documentRef() || licenseRef() || identifier()
  }

  const tokens = []
  while (hasMore()) {
    skipWhitespace()
    if (!hasMore()) break
    const token = parseToken()
    if (!token) throw new Error(`Unexpected \`${source[index]}\` at offset ${index}`)
    tokens.push(token)
  }
  return tokens
}

function parse(tokens) {
  let index = 0
  const hasMore = () => index < tokens.length
  const token = () => (hasMore() ? tokens[index] : null)
  const next = () => {
    if (!hasMore()) throw new Error()
    index += 1
  }
  const parseOperator = (operator) => {
    const current = token()
    if (current && current.type === 'OPERATOR' && operator === current.string) {
      next()
      return current.string
    }
  }
  const parseWith = () => {
    if (parseOperator('WITH')) {
      const current = token()
      if (current && current.type === 'EXCEPTION') {
        next()
        return current.string
      }
      throw new Error('Expected exception after `WITH`')
    }
  }
  const parseLicenseRef = () => {
    const begin = index
    let string = ''
    let current = token()
    if (current?.type === 'DOCUMENTREF') {
      next()
      string += `DocumentRef-${current.string}:`
      if (!parseOperator(':')) throw new Error('Expected `:` after `DocumentRef-...`')
    }
    current = token()
    if (current?.type === 'LICENSEREF') {
      next()
      string += `LicenseRef-${current.string}`
      return { license: string }
    }
    index = begin
  }
  const parseLicense = () => {
    const current = token()
    if (current && current.type === 'LICENSE') {
      next()
      const node = { license: current.string }
      if (parseOperator('+')) node.plus = true
      const exception = parseWith()
      if (exception) node.exception = exception
      return node
    }
  }
  const parseParenthesizedExpression = () => {
    if (!parseOperator('(')) return
    const expression = parseExpression()
    if (!parseOperator(')')) throw new Error('Expected `)`')
    return expression
  }
  const parseAtom = () => parseParenthesizedExpression() || parseLicenseRef() || parseLicense()
  const makeBinaryOpParser = (operator, nextParser) => () => {
    const left = nextParser()
    if (!left) return
    if (!parseOperator(operator)) return left
    const right = makeBinaryOpParser(operator, nextParser)()
    if (!right) throw new Error('Expected expression')
    return { left, conjunction: operator.toLowerCase(), right }
  }
  const parseAnd = makeBinaryOpParser('AND', parseAtom)
  const parseExpression = makeBinaryOpParser('OR', parseAnd)
  const node = parseExpression()
  if (!node || hasMore()) throw new Error('Syntax error')
  return node
}

export function validSpdxExpression(argument) {
  if (typeof argument !== 'string') return false
  const fatString = argument.trim() !== argument || /\s{2,}/.test(argument)
  if (fatString) return false
  try {
    parse(scan(argument))
    return true
  } catch {
    return false
  }
}
