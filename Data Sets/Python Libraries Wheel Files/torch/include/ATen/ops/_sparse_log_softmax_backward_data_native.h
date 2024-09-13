#pragma once

// @generated by torchgen/gen.py from NativeFunction.h

#include <c10/core/Scalar.h>
#include <c10/core/Storage.h>
#include <c10/core/TensorOptions.h>
#include <c10/util/Deprecated.h>
#include <c10/util/Optional.h>
#include <c10/core/QScheme.h>
#include <ATen/core/Reduction.h>
#include <ATen/core/Tensor.h>
#include <tuple>
#include <vector>


namespace at {
namespace native {
TORCH_API at::Tensor & _sparse_log_softmax_backward_data_out(const at::Tensor & grad_output, const at::Tensor & output, int64_t dim, const at::Tensor & self, at::Tensor & out);
TORCH_API at::Tensor log_softmax_backward_sparse_cpu(const at::Tensor & grad_output, const at::Tensor & output, int64_t dim, const at::Tensor & self);
TORCH_API at::Tensor log_softmax_backward_sparse_cuda(const at::Tensor & grad_output, const at::Tensor & output, int64_t dim, const at::Tensor & self);
} // namespace native
} // namespace at
