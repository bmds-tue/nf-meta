import { describe, expect, it } from 'vitest'
import { accessHeaders, splitToken } from '../access'

describe('splitToken', () => {
    it('takes the token out of the URL', () => {
        expect(splitToken('http://127.0.0.1:8080/?token=abc')).toEqual({ token: 'abc', url: 'http://127.0.0.1:8080/' })
    })

    it('keeps the other query parameters', () => {
        expect(splitToken('http://localhost:5180/?a=1&token=abc#x')).toEqual({ token: 'abc', url: 'http://localhost:5180/?a=1#x' })
    })

    it('finds no token in a plain URL', () => {
        expect(splitToken('http://localhost:5180/')).toEqual({ token: null, url: 'http://localhost:5180/' })
    })
})

describe('accessHeaders', () => {
    it('is empty without a token', () => {
        expect(accessHeaders()).toEqual({})
    })
})
