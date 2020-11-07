import numpy
import cupy

import scipy
import scipy.linalg


def cg(A, b, x0=None, tol=1e-5, maxiter=None, M=None, callback=None,
       atol=None):
    """Uses Conjugate Gradient iteration to solve ``Ax = b``.

    Args:
        A (cupy.ndarray or cupyx.scipy.sparse.spmatrix): The real or complex
            matrix of the linear system with shape ``(n, n)``. ``A`` must
            be a hermitian, positive definitive matrix.
        b (cupy.ndarray): Right hand side of the linear system with shape
            ``(n,)`` or ``(n, 1)``.
        x0 (cupy.ndarray): Starting guess for the solution.
        tol (float): Tolerance for convergence.
        maxiter (int): Maximum number of iterations.
        M (cupy.ndarray or cupyx.scipy.sparse.spmatrix): Preconditioner for
            ``A``. The preconditioner should approximate the inverse of ``A``.
        callback (function): User-specified function to call after each
            iteration. It is called as ``callback(xk)``, where ``xk`` is the
            current solution vector.
        atol (float): Tolerance for convergence.

    Returns:
        tuple:
            It returns ``x`` (cupy.ndarray) and ``info`` (int) where ``x`` is
            the converged solution and ``info`` provides convergence
            information.

    .. seealso:: :func:`scipy.sparse.linalg.cg`
    """
    if A.ndim != 2 or A.shape[0] != A.shape[1]:
        raise ValueError('expected square matrix (shape: {})'.format(A.shape))
    if A.dtype.char not in 'fdFD':
        raise TypeError('unsupprted dtype (actual: {})'.format(A.dtype))
    n = A.shape[0]
    if not (b.shape == (n,) or b.shape == (n, 1)):
        raise ValueError('b has incompatible dimensins')
    b = b.astype(A.dtype).ravel()
    if n == 0:
        return cupy.empty_like(b), 0
    b_norm = cupy.linalg.norm(b)
    if atol is None:
        if b_norm == 0:
            atol = tol
        else:
            atol = tol * float(b_norm)
    else:
        atol = max(float(atol), tol * float(b_norm))
    if x0 is None:
        x = cupy.zeros((n,), dtype=A.dtype)
    else:
        if not (x0.shape == (n,) or x0.shape == (n, 1)):
            raise ValueError('x0 has incompatible dimensins')
        x = x0.astype(A.dtype).ravel()
    if maxiter is None:
        maxiter = n * 10

    def matvec(x): return A @ x

    if M is None:
        def psolve(x): return x
    else:
        def psolve(x): return M @ x
        if A.shape != M.shape:
            raise ValueError('matrix and preconditioner have different shapes')

    r = b - matvec(x)
    iters = 0
    rho = 0
    while iters < maxiter:
        z = psolve(r)
        rho1 = rho
        rho = cupy.dot(r.conj(), z)
        if iters == 0:
            p = z
        else:
            beta = rho / rho1
            p = z + beta * p
        q = matvec(p)
        alpha = rho / cupy.dot(p.conj(), q)
        x = x + alpha * p
        r = r - alpha * q
        iters += 1
        if callback is not None:
            callback(x)
        resid = cupy.linalg.norm(r)
        if resid <= atol:
            break

    info = 0
    if iters == maxiter and not (resid <= atol):
        info = iters

    return x, info


def gmres(A, b, x0=None, tol=1e-5, restart=None, maxiter=None, M=None,
          callback=None, atol=None, callback_type=None):
    """Uses Generalized Minimal RESidual iteration to solve ``Ax = b``.

    Args:
        A (cupy.ndarray or cupyx.scipy.sparse.spmatrix): The real or complex
            matrix of the linear system with shape ``(n, n)``.
        b (cupy.ndarray): Right hand side of the linear system with shape
            ``(n,)`` or ``(n, 1)``.
        x0 (cupy.ndarray): Starting guess for the solution.
        tol (float): Tolerance for convergence.
        restart (int): Number of iterations between restarts. Larger values
            increase iteration cost, but may be necessary for convergence.
        maxiter (int): Maximum number of iterations.
        M (cupy.ndarray or cupyx.scipy.sparse.spmatrix): Preconditioner for
            ``A``. The preconditioner should approximate the inverse of ``A``.
        callback (function): User-specified function to call on every restart.
            It is called as ``callback(arg)``, where ``arg`` is selected by
            ``callback_type``.
        callback_type (str): 'x' or 'pr_norm'. If 'x', the current solution
            vector is used as an argument of callback function. if `pr_norm`,
            relative (preconditioned) residual norm is used as an arugment.
        atol (float): Tolerance for convergence.

    Returns:
        tuple:
            It returns ``x`` (cupy.ndarray) and ``info`` (int) where ``x`` is
            the converged solution and ``info`` provides convergence
            information.

    Reference:
        M. Wang, H. Klie, M. Parashar and H. Sudan, "Solving Sparse Linear
        Systems on NVIDIA Tesla GPUs", ICCS 2009 (2009).

    .. seealso:: :func:`scipy.sparse.linalg.gmres`
    """
    if A.ndim != 2 or A.shape[0] != A.shape[1]:
        raise ValueError('expected square matrix (shape: {})'.format(A.shape))
    if A.dtype.char not in 'fdFD':
        raise TypeError('unsupprted dtype (actual: {})'.format(A.dtype))
    n = A.shape[0]
    if not (b.shape == (n,) or b.shape == (n, 1)):
        raise ValueError('b has incompatible dimensins')
    b = b.astype(A.dtype).ravel()
    if n == 0:
        return cupy.empty_like(b), 0
    b_norm = cupy.linalg.norm(b)
    if b_norm == 0:
        return b, 0
    if atol is None:
        atol = tol * float(b_norm)
    else:
        atol = max(float(atol), tol * float(b_norm))
    if x0 is None:
        x = cupy.zeros((n,), dtype=A.dtype)
    else:
        if not (x0.shape == (n,) or x0.shape == (n, 1)):
            raise ValueError('x0 has incompatible dimensins')
        x = x0.astype(A.dtype).ravel()
    if maxiter is None:
        maxiter = n * 10
    if restart is None:
        restart = 20
    restart = min(restart, n)

    if callback_type is None:
        callback_type = 'pr_norm'
    if callback_type not in ('x', 'pr_norm'):
        raise ValueError('Unknow callback_type: {}'.format(callback_type))
    if callback is None:
        callback_type = None

    def matvec(x): return A @ x

    if M is None:
        def psolve(x): return x
    else:
        def psolve(x): return M @ x
        if A.shape != M.shape:
            raise ValueError('matrix and preconditioner have different shapes')

    V = cupy.empty((n, restart), dtype=A.dtype, order='F')
    H = cupy.zeros((restart+1, restart), dtype=A.dtype, order='F')
    e = numpy.zeros((restart+1,), dtype=A.dtype)

    iters = 0
    while True:
        mx = psolve(x)
        r = b - matvec(mx)
        r_norm = cupy.linalg.norm(r)
        if callback_type == 'x':
            callback(mx)
        elif callback_type == 'pr_norm' and iters > 0:
            callback(r_norm / b_norm)
        if r_norm <= atol or iters >= maxiter:
            break
        V[:, 0] = r / r_norm
        e[0] = r_norm

        # Arnoldi iteration
        for j in range(restart):
            z = psolve(V[:, j])
            u = matvec(z)
            H[:j+1, j] = V[:, :j+1].conj().T @ u
            u -= V[:, :j+1] @ H[:j+1, j]
            H[j+1, j] = cupy.linalg.norm(u)
            if j+1 < restart:
                V[:, j+1] = u / H[j+1, j]

        # Note: The least-square solution to equation Hy = e is computed on CPU
        # because it is faster if tha matrix size is small.
        ret = scipy.linalg.lstsq(cupy.asnumpy(H), e)
        y = cupy.array(ret[0])
        x += V @ y
        iters += restart

    info = 0
    if iters == maxiter and not (r_norm <= atol):
        info = iters
    return mx, info
