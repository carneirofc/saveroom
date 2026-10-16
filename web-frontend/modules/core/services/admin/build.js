export default (client) => {
  return {
    get() {
      return client.get('/admin/build/')
    },
  }
}
