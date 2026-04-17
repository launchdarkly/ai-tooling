export default class EchoOutputProvider {
  id = () => "echo-output";

  callApi = async (prompt, context) => {
    return {
      output: context.vars.canned_output,
      tokenUsage: { total: 0, prompt: 0, completion: 0 },
      cost: 0,
    };
  };
}
